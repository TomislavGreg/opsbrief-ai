"""The default offline provider: no model, a composed narrative.

The default build runs offline. Rather than echo the prompt material back (which
reads as scaffolding, not a summary), this provider signals the generation layer to
compose a short narrative from the structured picture itself, with no language
model involved.

It carries no model and phrases nothing: the :attr:`composes_narrative` marker tells
:func:`~opsbrief.brief.generate.generate_brief` and
:func:`~opsbrief.incidents.summary.generate_incident_summary` to build the summary
deterministically from the context they already hold, which only they can see. Its
:meth:`complete` is therefore never used on that path; it returns an empty response
so that any caller ignoring the marker degrades to the deterministic picture rather
than to made-up text.
"""

from opsbrief.ai.schema import CompletionRequest, CompletionResponse


class DeterministicNarrativeProvider:
    """A provider that composes summaries from structure rather than a model.

    See the module docstring. The :attr:`composes_narrative` attribute is the
    contract the generation layer checks; the rest of the provider protocol is
    satisfied so it can be selected and injected like any other provider.
    """

    #: Stable identifier for the provider, recorded as the "model" behind a summary
    #: it composes, so a deterministic summary traces to this provider by name.
    name = "deterministic"

    #: Marks that the generation layer should compose the summary from the structured
    #: picture rather than ask this provider to phrase it. Read with ``getattr`` so
    #: the provider protocol itself need not carry the attribute.
    composes_narrative = True

    def complete(self, request: CompletionRequest) -> CompletionResponse:
        """Return an empty completion; this provider phrases nothing with a model.

        The generation layer composes the narrative itself when
        :attr:`composes_narrative` is set, so this is not called on that path. It
        returns an empty response for defensive safety rather than inventing text.
        """
        return CompletionResponse(text="", model=self.name)
