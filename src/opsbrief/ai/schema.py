"""The AI completion contract.

OpsBrief AI uses a language model for one narrow job: turning material the
service has already assembled into readable prose. It never asks a model what
counts as a risk, how urgent something is, or which events matter — those are
decided by deterministic rules. The contract here reflects that narrow role: a
:class:`CompletionRequest` carries the instruction and the material, a
:class:`CompletionResponse` carries the text a provider produced and the model
that produced it.

Requests are bounded on purpose. ``max_output_tokens`` caps how much a model may
return, and the length limits keep a prompt from growing without bound, so a
provider is always given a constrained, well-formed request rather than an open
one.
"""

from pydantic import BaseModel, ConfigDict, Field

#: Largest prompt, in characters, the contract will carry in one field.
MAX_PROMPT_LENGTH = 20_000

#: Default cap on how many tokens a provider may return for one request.
DEFAULT_MAX_OUTPUT_TOKENS = 512

#: Largest output cap a request may ask for.
MAX_OUTPUT_TOKENS_LIMIT = 4_096


class CompletionRequest(BaseModel):
    """What the service asks a provider to turn into prose.

    ``instructions`` say what to do — the task the model performs, phrased by the
    service, never by a producer. ``input`` is the material to work on, which the
    service has already assembled and, where necessary, redacted. The two are kept
    apart so a provider can treat the instruction as trusted framing and the
    input as data. ``max_output_tokens`` and ``temperature`` bound and steer the
    result: the default temperature is zero because the service prefers a stable,
    repeatable phrasing over a varied one.
    """

    model_config = ConfigDict(extra="forbid")

    instructions: str = Field(
        min_length=1,
        max_length=MAX_PROMPT_LENGTH,
        description="The task the model performs, phrased by the service.",
    )
    input: str = Field(
        default="",
        max_length=MAX_PROMPT_LENGTH,
        description="The material to turn into prose, already assembled by the service.",
    )
    max_output_tokens: int = Field(
        default=DEFAULT_MAX_OUTPUT_TOKENS,
        ge=1,
        le=MAX_OUTPUT_TOKENS_LIMIT,
        description="Upper bound on how many tokens the provider may return.",
    )
    temperature: float = Field(
        default=0.0,
        ge=0.0,
        le=2.0,
        description="How much the provider may vary its phrasing; zero is repeatable.",
    )


class CompletionResponse(BaseModel):
    """What a provider returns for a request.

    ``text`` is the prose the model produced; it may be empty, because an empty
    completion is a real outcome a caller must handle rather than a contract
    violation. ``model`` names the model that produced the text, so a generated
    statement can be traced to the model behind it just as a risk is traced to the
    rule behind it. The text is untrusted: a caller validates and constrains it
    before using it, exactly as it would any other external data.
    """

    model_config = ConfigDict(extra="forbid")

    text: str = Field(
        description="The prose the provider produced; may be empty.",
    )
    model: str = Field(
        min_length=1,
        max_length=128,
        description="Identifier of the model that produced the text, for traceability.",
    )
