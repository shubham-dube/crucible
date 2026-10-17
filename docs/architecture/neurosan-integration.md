# Neuro-SAN integration notes (verified against source, neuro-san 0.7.12)

All code that imports `neuro_san` lives in `src/crucible/integrations/neurosan/`. Re-verify this page when bumping the pinned version.

## Loading networks
- `neuro_san.internals.graph.persistence.agent_network_restorer.AgentNetworkRestorer().restore(file_reference=path)` → `AgentNetwork`; applies includes + `commondefs` filters.
- `AgentNetwork.get_config()`, `get_agent_tool_spec(name)`, `find_front_man()` (front man = first entry of `tools`; must not have `class`/`toolbox`).
- Validators: `neuro_san.internals.validation.network.manifest_network_validator.ManifestNetworkValidator(external_network_names, mcp_servers, network_name)`; also `CyclesNetworkValidator`. Each `validate(config_dict) -> list[str]`.
- CLI equivalent: `python -m neuro_san.client.hocon_validator_cli file.hocon`.

## Agent spec keys that matter to Crucible
`name`, `function{description, parameters}`, `instructions`, `tools` (internal names, `/external`, URLs, MCP), `class` (coded tool), `toolbox`, `args`, `allow{to_downstream, from_downstream, to_upstream, to_tracing}.sly_data`, `llm_config`, `max_message_history`, `middleware`. Top level: `llm_config`, `commondefs`, `max_steps`, `max_execution_seconds`, `max_attempts`, `request_timeout_seconds`, `metadata`, `sly_data_schema`.

## Running conversations
```python
from neuro_san.client.agent_session_factory import AgentSessionFactory
from neuro_san.client.streaming_input_processor import StreamingInputProcessor

session = AgentSessionFactory().create_session("direct", "/abs/path/net.hocon", use_direct=True, metadata={...})
session.reset()  # per turn for DirectAgentSession
sip = StreamingInputProcessor(session=session)
req = sip.formulate_chat_request(text, sly_data, chat_context, {"chat_filter_type": "MAXIMAL"})
for resp in session.streaming_chat(req):
    msg = resp["response"]  # ChatMessage dict: type, text, origin, structure, sly_data, chat_context
```
- Message types: SYSTEM=1, HUMAN=2, AI=4, AGENT=100, AGENT_FRAMEWORK=101 (final; carries returned sly_data + chat_context), AGENT_TOOL_RESULT=103, AGENT_PROGRESS=104.
- MAXIMAL AGENT messages include `"Invoking: `X` with:"` (structure `invoking_start`, `invoked_agent_name`, `params`), `"Received arguments:"`, `"Got result:"` (`tool_end`, `tool_error`, `tool_output`), plus token accounting structures.
- Env for coded tools: `AGENT_TOOL_PATH` = dir containing `<network>/<module>.py`. **Gotcha:** when it is a filesystem path, Neuro-SAN converts it into a dotted module path relative to the longest matching `PYTHONPATH` entry, so its parent dir must be in `PYTHONPATH` (env) *and* importable (`sys.path`). Crucible's integration layer sets this up automatically.

## Chaos hook
`AGENT_ACTIVATION_PREPPER_CLASSES="pkg.Mod.Class"` (space separated). A prepper implements `is_applicable(agent_tool_spec)` and `prepare_activation(...)`, returning an activation; inserted before the stock class prepper. Coded tool invocation path: `AbstractClassActivation.attempt_invoke(coded_tool, args, sly_data)`; exceptions become `"Error: ..."` tool output (swallowed).

## Prompt capture
Exact LLM inputs are not in the stream. Use LangChain's `register_configure_hook(ContextVar, inheritable=True)` with a handler implementing `on_chat_model_start` (same mechanism as Neuro-SAN's Langfuse tracing context). Fallback: OpenInference instrumentation.

## LLM config
`class: anthropic` (env `ANTHROPIC_API_KEY`, aliases `claude-sonnet`, `claude-haiku`, `claude-opus`), `class: gemini` (env `GOOGLE_API_KEY`, e.g. `gemini-3-flash`, temperature 1.0). A full LangChain class path is also accepted as `class` — that is how `ScriptedChatModel` is plugged in.

## Existing test stack (we extend, not replace)
`neuro_san.test`: test-case HOCON (`agent`, `connections`, `success_ratio`, `interactions[{text, sly_data, response{text|sly_data|structure: {value|keywords|gist|less|greater...}}}]`), `DataDrivenTestsDriver`, `AgentEvaluatorFactory`, gist evaluator, Assessor. Studio has an `agent_network_test_generator` network.

## Sandbox gotcha
`ChatMockLlm` uses tiktoken, whose encoding download is blocked in the cloud sandbox. Crucible uses its own `ScriptedChatModel` (no tiktoken).
