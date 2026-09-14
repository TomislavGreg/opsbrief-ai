"""Fitting rendered prompt material into a bounded character budget.

The material a model is shown must stay within
:data:`~opsbrief.ai.schema.MAX_PROMPT_LENGTH`. The wrong way to enforce that is
to render everything and slice the string: the cut lands mid-line, drops whole
sections that happen to come last (an incident's resolution note, a brief's
omission notes), and leaves the structured output claiming a complete picture the
model never saw. This module enforces the bound the right way. A fixed preamble
and trailer are kept whole; prioritised sections are filled with as many
*complete* item lines as fit, most important first; and each section that had to
drop items says so, both in the material shown to the model and in a
:class:`SectionFit` the caller can turn into a warning. It never emits a partial
record.

The common case is unchanged: when the whole document already fits, it is
rendered exactly as before, byte for byte, and every section reports itself
complete. Only genuinely oversized material is trimmed.
"""

from collections.abc import Callable, Sequence
from dataclasses import dataclass

from opsbrief.ai.schema import MAX_PROMPT_LENGTH


@dataclass(frozen=True)
class Section:
    """One prioritised, budget-fillable block of the material.

    ``items`` are complete lines in priority order: the front is kept first, so
    the most important items (the most urgent risks, the newest events, the
    earliest timeline entries) survive when the budget is tight. ``header`` labels
    the block when it has items; ``none_line`` stands in when it has none.
    ``omission_note`` renders the one line, appended after the kept items, that
    tells the model how many items were dropped; it is called as
    ``omission_note(shown, total)`` and only when ``shown < total``.
    """

    key: str
    header: str
    items: Sequence[str]
    none_line: str
    omission_note: Callable[[int, int], str]


@dataclass(frozen=True)
class SectionFit:
    """How much of one section reached the model: ``shown`` of ``total`` items."""

    key: str
    shown: int
    total: int

    @property
    def omitted(self) -> int:
        """How many items the budget dropped from this section."""
        return self.total - self.shown

    @property
    def truncated(self) -> bool:
        """Whether any item was dropped to fit the budget."""
        return self.shown < self.total


@dataclass(frozen=True)
class BudgetedMaterial:
    """Rendered material within the budget, plus what each section had to drop."""

    text: str
    fits: tuple[SectionFit, ...]

    @property
    def truncated(self) -> bool:
        """Whether any section dropped items to fit the budget."""
        return any(fit.truncated for fit in self.fits)

    def fit(self, key: str) -> SectionFit:
        """Return the fit for the section with ``key``."""
        for fit in self.fits:
            if fit.key == key:
                return fit
        raise KeyError(key)


class _Builder:
    """Accumulates lines and tracks the length of their newline join exactly."""

    def __init__(self) -> None:
        self.lines: list[str] = []
        self.used = 0

    def _cost(self, line: str) -> int:
        # The first line carries no preceding newline; every later line adds one.
        return len(line) if not self.lines else len(line) + 1

    def add(self, line: str) -> None:
        self.used += self._cost(line)
        self.lines.append(line)

    def fits(self, line: str, budget: int, *, reserve: int) -> bool:
        """Whether ``line`` fits with ``reserve`` characters still held back."""
        return self.used + self._cost(line) + reserve <= budget

    def text(self) -> str:
        return "\n".join(self.lines)


def _blocks_text(
    preamble: Sequence[str],
    sections: Sequence[Section],
    trailer_blocks: Sequence[Sequence[str]],
) -> str:
    """Render the whole document with every item shown, blocks blank-line separated."""
    blocks: list[list[str]] = [list(preamble)]
    for section in sections:
        if section.items:
            blocks.append([section.header, *section.items])
        else:
            blocks.append([section.none_line])
    blocks += [list(block) for block in trailer_blocks if block]
    return "\n\n".join("\n".join(block) for block in blocks)


def render_budgeted(
    preamble: Sequence[str],
    sections: Sequence[Section],
    trailer_blocks: Sequence[Sequence[str]] = (),
    *,
    budget: int = MAX_PROMPT_LENGTH,
) -> BudgetedMaterial:
    """Render material within ``budget`` characters, dropping whole items only.

    ``preamble`` (the header and status lines) and ``trailer_blocks`` (an
    incident's resolution note, a brief's notes) are kept whole: they carry the
    current state and the disclosures a reader must see, so room for them is
    reserved before any section is filled. Each :class:`Section` is then filled in
    turn with as many complete ``items`` as fit, most important first; a section
    that drops items gains an ``omission_note`` line so the model is not misled
    into implying a complete picture. The returned :class:`SectionFit` for each
    section records how many items reached the model, so the caller can raise a
    matching warning.

    When the whole document already fits, it is returned unchanged and every
    section reports itself complete, so the ordinary small prompt is byte for byte
    what it was before budgeting. ``budget`` is expected to exceed the fixed
    material (preamble, trailer, headers and omission notes); with the default
    :data:`~opsbrief.ai.schema.MAX_PROMPT_LENGTH` and the bounded material this
    service assembles, only the variable sections can ever overflow it.
    """
    full = _blocks_text(preamble, sections, trailer_blocks)
    if len(full) <= budget:
        return BudgetedMaterial(
            text=full,
            fits=tuple(SectionFit(s.key, len(s.items), len(s.items)) for s in sections),
        )

    builder = _Builder()
    for line in preamble:
        builder.add(line)

    # Reserve room, up front, for everything that must survive: a worst-case
    # omission note for every section that has items (using the totals for both
    # numbers gives a safe upper bound on the note's length, since the real
    # shown/omitted counts never have more digits), and every trailer block with
    # its blank separator. The reserve is released as each piece is placed.
    def worst_note_cost(section: Section) -> int:
        total = len(section.items)
        return len(section.omission_note(total, total)) + 1

    reserve = sum(worst_note_cost(s) for s in sections if s.items)
    for block in trailer_blocks:
        if block:
            reserve += 1 + sum(len(line) + 1 for line in block)

    fits: list[SectionFit] = []
    for section in sections:
        total = len(section.items)
        if total == 0:
            builder.add("")
            builder.add(section.none_line)
            fits.append(SectionFit(section.key, 0, 0))
            continue

        note_reserve = worst_note_cost(section)
        # This section's own omission note stays reserved while its items are
        # placed, so there is always room for it if the section ends up trimmed.
        reserve -= note_reserve
        builder.add("")
        builder.add(section.header)
        shown = 0
        for item in section.items:
            if builder.fits(item, budget, reserve=reserve + note_reserve):
                builder.add(item)
                shown += 1
            else:
                break
        if shown < total:
            builder.add(section.omission_note(shown, total))
        fits.append(SectionFit(section.key, shown, total))

    for block in trailer_blocks:
        if not block:
            continue
        reserve -= 1 + sum(len(line) + 1 for line in block)
        builder.add("")
        for line in block:
            builder.add(line)

    return BudgetedMaterial(text=builder.text(), fits=tuple(fits))
