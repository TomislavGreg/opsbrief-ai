"""How a generated output's prose was produced, kept separate from confidence.

A daily brief and an incident summary each carry two independent judgements about
their prose, and conflating them is what let a model quietly contradict the facts.

- ``confidence`` (see :mod:`opsbrief.warnings`) measures how complete the evidence
  behind the picture is: whether events are missing, the view was bounded, the
  prompt was trimmed. It says nothing about whether the words match the facts.
- :class:`SummaryStatus` measures the provenance of the prose itself: whether the
  summary was composed deterministically from the structured picture, phrased by a
  language model and left unverified, or not produced at all.

The two are orthogonal. A picture built from complete evidence (high confidence)
can still carry an unverified model summary, and a picture with a gap in its
evidence (low confidence) can still carry a deterministic summary. Keeping them
separate means a model saying "nothing is blocked" over a deterministic blocked
risk is labelled unverified rather than allowed to raise the reader's trust in the
words.

No verification of model prose against the facts is claimed anywhere: there is no
semantic check, and a citation whitelist is not treated as proof. Model prose is
labelled unverified, full stop, and the structured risks, actions and evidence a
reader acts on are always shown alongside it.
"""

from enum import StrEnum


class SummaryStatus(StrEnum):
    """How a generated output's prose summary was produced and how far to trust it.

    This is deliberately separate from :class:`opsbrief.warnings.Confidence`, which
    measures evidence completeness. This measures only the provenance of the prose.
    """

    #: Composed by the service from the structured picture, with no model. It
    #: restates the deterministic facts, so it is trustworthy by construction rather
    #: than something a reader must check against them.
    DETERMINISTIC = "deterministic"
    #: Phrased by a language model and NOT checked against the structured facts. The
    #: model may contradict them, so a reader weighs the prose against the risks,
    #: actions and evidence, which are always shown.
    MODEL_UNVERIFIED = "model_unverified"
    #: No summary was produced (the provider was unavailable or returned nothing),
    #: so the output carries the deterministic picture with an empty summary.
    UNAVAILABLE = "unavailable"
