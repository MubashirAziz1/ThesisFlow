"""Run lifecycle service layer.

Centralizes the business logic for creating runs, formatting SSE
frames, and consuming stream bridge events. 
"""

from __future__ import annotations

import asyncio
import json
import logging
from dataclasses import replace
from typing import Any

from fastapi import HTTPException, Request

from langchain_core.messages import BaseMessage, HumanMessage
from langchain_core.messages.utils import convert_to_messages


from app.gateway.run_models import RunCreateRequest
from packages.harness.thesisflow.utils.thread_id import validate_thread_id
from packages.harness.thesisflow.runtime.stream_modes import normalize_stream_modes
from packages.harness.thesisflow.runtime.runs.schemas import DisconnectMode

logger = logging.getLogger(_name__)

_DEFAULT_ASSISTANT_ID = "lead_agent"


def normalize_input(raw_input: dict[str, Any] | None) -> dict[str, Any]:
    """ Convert LangGraph Platform input format to LangChain state dict. """

    if raw_input is None:
        return {}
    result = raw_input
    messages = raw_input.get("messages")
    if messages and isinstance(messages, list):
        converted: list[Any] = []
        for index, msg in enumerate(messages):
            if isinstance(msg, BaseMessage):
                converted.append(msg)
            elif isinstance(msg, dict):
                try:
                    converted.extend(convert_to_messages([msg]))
                except (ValueError, TypeError, NotImplementedError) as exc:
                    raise HTTPException(
                        status_code=400,
                        detail=f"Invalid message at input.messages[{index}]: {exc}",
                    ) from exc
            else:
                converted.append(msg)

        # if not trusted_internal:
        #     converted = [_strip_external_message_metadata(message) for message in converted]
        
        result = {**raw_input, "messages": converted}

    # if not trusted_internal:
    #     delegations = result.get("delegations")
    #     if isinstance(delegations, list):
    #         cleaned = [_strip_external_delegation_verdict(entry) for entry in delegations]
    #         if cleaned != delegations:
    #             result = {**result, "delegations": cleaned}

    return result


def build_run_config(thread_id: str, *, assistant_id: str | None = None) -> dict[str, Any]:
    
    config: dict[str, Any] = {
        "configurable": {
            "thread_id": thread_id
        }
    }

    if assistant_id and assistant_id != _DEFAULT_ASSISTANT_ID:
        normalized = assistant_id.strip().lower().replace("_", "-")
        if not normalized or not re.fullmatch(r"[a-z0-9-]+", normalized):
            raise ValueError(f"Invalid assistant_id {assistant_id!r}: must contain only letters, digits, and hyphens after normalization.")

        config["configurable"]["agent_name"] = normalized

    return config

async def _load_scope_agent_config(
    *,
    assistant_id: str | None,
    user_id: str | None,
) -> Any | None:
    
    if not assistant_id or assistant_id == _DEFAULT_ASSISTANT_ID:
        return None
    normalized = assistant_id.strip().lower().replace("_", "-")
    try:
        return await asyncio.to_thread(
            load_agent_config,
            normalized,
            user_id=user_id,
        )
    except (FileNotFoundError, ValueError) as exc:
        raise HTTPException(
            status_code=422,
            detail="knowledge_scope assistant configuration could not be resolved",
        ) from exc





async def start_run(
    body: RunCreateRequest,
    thread_id: str,
    request: Request,
    *,
    idempotency_key: str | None = None,
    require_existing_thread: bool = False,
) -> RunRecord:
    """ Create a RunRecord and launch the background agent task. """

    try:
        validate_thread_id(thread_id)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    

    stream_modes = normalize_stream_modes(body.stream_mode)
    disconnect = DisconnectMode.cancel if body.on_disconnect == "cancel" else DisconnectMode.continue_

    # Explicitly mention the model to use here.
    

    # user = getattr(request.state, "user", None)

    # async def thread_access_allowed() -> bool:
    #     if user is None:
    #         if not require_existing_thread:
    #             return True
    #         return await run_ctx.thread_store.get(thread_id) is not None
    #     allowed = await run_ctx.thread_store.check_access(
    #         thread_id,
    #         str(user.id),
    #         require_existing=require_existing_thread,
    #     )
    #     if not allowed and owner_user_id and getattr(user, "system_role", None) == INTERNAL_SYSTEM_ROLE:
    #         # Channel workers may also act for the connection owner named in
    #         # the trusted header (e.g. claiming a legacy default-owned channel
    #         # thread for its real owner).
    #         allowed = await run_ctx.thread_store.check_access(
    #             thread_id,
    #             owner_user_id,
    #             require_existing=require_existing_thread,
    #         )
    #     return allowed

    # if not await thread_access_allowed():
    #     raise HTTPException(status_code=404, detail=f"Thread {thread_id} not found")

    # owner_context_token = set_current_user(SimpleNamespace(id=owner_user_id)) if owner_user_id else None
    try:
        agent_factory = resolve_agent_factory(body.assistant_id)


        # command = getattr(body, "command", None)
        # if command and command.get("resume") is not None:
        #     graph_input = Command(resume=command["resume"])
        # else:
 
        graph_input = normalize_input(body.input)


        
        #run_metadata = dict(body.metadata) if isinstance(body.metadata, dict) else {}
        #run_metadata[DEERFLOW_TRACE_METADATA_KEY] = ensure_trace_id()

        config = build_run_config(thread_id, assistant_id=body.assistant_id)

        ##If the user asks to resume froim the previous session or to continue from the specific checkpoint, then its needed.
        #await apply_checkpoint_to_run_config(config, body=body, thread_id=thread_id, request=request)

        # replay_kind = run_metadata.get("replay_kind")
        # target_message_id = run_metadata.get("regenerate_from_message_id")
        
        ## USe the code below for further context recovery or for thesis case.
        # scope_graph_input = graph_input if isinstance(graph_input, dict) else {"messages": []}
        # scope_messages = scope_graph_input.get("messages")
        # candidate_has_scope = isinstance(scope_messages, list) and any(isinstance(message, BaseMessage) and KNOWLEDGE_SCOPE_KEY in message.additional_kwargs for message in scope_messages)
        # current_human_message = _current_human_message(graph_input)
        # current_message_has_scope = current_human_message is not None and KNOWLEDGE_SCOPE_KEY in current_human_message.additional_kwargs
        # replay_requires_scope_recovery = isinstance(graph_input, Command) or (isinstance(target_message_id, str) and bool(target_message_id) and (replay_kind != "edit" or not current_message_has_scope))
        # is_human_input_response = current_human_message is not None and "human_input_response" in current_human_message.additional_kwargs
        
        
        # Clarification and edit-replay messages may intentionally replace the
        # source scope. If either client omits its current selector snapshot,
        # inherit the source turn's authoritative scope instead of widening the
        # run to every operator-approved dataset. Other replay paths always use
        # server recovery regardless of client input.
        
        # is_scope_recovery = replay_requires_scope_recovery or (is_human_input_response and not current_message_has_scope)
        # recovery_scope = (
        #     await _recover_run_knowledge_scope(
        #         request,
        #         thread_id=thread_id,
        #         target_message_id=(target_message_id if isinstance(target_message_id, str) else None),
        #     )
        #     if is_scope_recovery
        #     else None
        # )
        
        
        agent_config = (
            await _load_scope_agent_config(
                assistant_id=body.assistant_id,
                user_id=owner_user_id or (str(user.id) if user is not None else None),
            )
            if candidate_has_scope or recovery_scope is not None
            else None
        )
        admitted_knowledge_scope = admit_message_knowledge_scope(
            scope_graph_input,
            assistant_id=body.assistant_id,
            app_config=run_ctx.app_config or get_app_config(),
            agent_config=agent_config,
            recovery_scope=recovery_scope,
            recovery=is_scope_recovery,
        )
        if admitted_knowledge_scope is not None:
            await _validate_scope_thread_binding(
                run_ctx,
                thread_id=thread_id,
                assistant_id=body.assistant_id,
            )
        run_record_input = _canonical_run_record_input(body.input, graph_input)

        # Merge DeerFlow-specific context overrides into both ``configurable`` and ``context``.
        # The ``context`` field is a custom extension for the langgraph-compat layer
        # that carries agent configuration (model_name, thinking_enabled, etc.).
        # Only agent-relevant keys are forwarded; unknown keys (e.g. thread_id) are ignored.
        merge_run_context_overrides(config, getattr(body, "context", None), internal=is_internal_caller)
        if not is_internal_caller:
            # ``body.config`` is free-form and copied verbatim by
            # ``build_run_config``; scrub internal-only keys smuggled there.
            strip_internal_context_keys(config)
        internal_owner_user = await resolve_trusted_internal_owner_for_attribution(request, owner_user_id)
        inject_authenticated_user_context(
            config,
            request,
            internal_owner_user=internal_owner_user,
            request_context=getattr(body, "context", None),
        )

        conversation_references = list(getattr(body, "conversation_references", None) or [])
        if conversation_references:
            from app.gateway.conversation_access import prepare_conversation_reader

            prepared = prepare_conversation_reader(
                conversation_references,
                request=request,
                user_id=owner_user_id or (str(user.id) if user is not None else None),
                run_context=run_ctx,
                run_manager=run_mgr,
                app_config=get_app_config(),
            )
            reader, source_ids = prepared
            run_ctx = replace(run_ctx, conversation_reader=reader)
            if isinstance(graph_input, dict):
                reference_messages = graph_input.get("messages")
                if reference_messages is None:
                    reference_messages = []
                if not isinstance(reference_messages, list):
                    raise HTTPException(status_code=422, detail="input.messages must be a list")
                # Reference IDs are user-selected data. Keep them out of the
                # system prompt and grant no authority from this persisted hint.
                graph_input = {
                    **graph_input,
                    "messages": [
                        *reference_messages,
                        HumanMessage(
                            content="Read-only conversation references for this run: " + json.dumps(source_ids),
                            additional_kwargs={"hide_from_ui": True},
                        ),
                    ],
                }
        # Resolve and pin the thread's project context once per run (spec
        # §7.1): middlewares and tools read only this server-owned snapshot —
        # nothing re-resolves membership mid-run, and admission never writes
        # membership (§10.7). Resolution failure degrades to unassigned with a
        # warning inside the resolver; it never fails the run.
        project_context = await resolve_project_context(
            run_ctx.thread_store,
            getattr(request.app.state, "project_repo", None),
            thread_id,
            getattr(request.app.state, "project_document_repo", None),
        )
        if project_context is not None:
            config["context"][PROJECT_CONTEXT_KEY] = project_context

        async def run_after_metadata(record: RunRecord) -> None:
            metadata_task = asyncio.create_task(
                _ensure_thread_metadata(
                    run_ctx,
                    record,
                    owner_user_id=owner_user_id,
                    require_existing_thread=require_existing_thread,
                )
            )
            abort_task = asyncio.create_task(record.abort_event.wait())
            metadata_failure_logged = False
            metadata_failure: Exception | None = None
            try:
                done, _ = await asyncio.wait(
                    (metadata_task, abort_task),
                    timeout=_THREAD_METADATA_SETUP_TIMEOUT_SECONDS,
                    return_when=asyncio.FIRST_COMPLETED,
                )
                if metadata_task in done:
                    try:
                        metadata_task.result()
                    except asyncio.CancelledError:
                        pass
                    except Exception as exc:
                        metadata_failure_logged = True
                        metadata_failure = exc
                        logger.warning(
                            "Failed to ensure thread_meta for %s%s",
                            sanitize_log_param(thread_id),
                            "" if require_existing_thread else " (non-fatal)",
                            exc_info=True,
                        )
                elif abort_task not in done:
                    logger.warning(
                        "Timed out ensuring thread_meta for %s after %.1fs",
                        sanitize_log_param(thread_id),
                        _THREAD_METADATA_SETUP_TIMEOUT_SECONDS,
                    )
                    if require_existing_thread:
                        metadata_failure = TimeoutError("Timed out verifying existing thread metadata")
            finally:
                if metadata_task.done():
                    if not metadata_failure_logged:
                        _log_thread_metadata_task_result(metadata_task, thread_id=thread_id)
                else:
                    metadata_task.cancel()
                    metadata_task.add_done_callback(
                        lambda task: _log_thread_metadata_task_result(
                            task,
                            thread_id=thread_id,
                        )
                    )
                if not abort_task.done():
                    abort_task.cancel()
                    abort_task.add_done_callback(_consume_task_result)
            if metadata_failure is not None and require_existing_thread:
                await run_mgr.fail_start_if_pending(
                    record.run_id,
                    error=str(metadata_failure),
                )
            # Continue through run_agent even after metadata abort, timeout,
            # or strict verification failure:
            # its startup barrier is the single path that turns pending
            # cancellation into no-agent-construction plus publish_end.
            await run_agent(
                bridge,
                run_mgr,
                record,
                ctx=run_ctx,
                agent_factory=agent_factory,
                graph_input=graph_input,
                config=config,
                stream_modes=stream_modes,
                stream_subgraphs=body.stream_subgraphs,
                interrupt_before=body.interrupt_before,
                interrupt_after=body.interrupt_after,
                knowledge_scope=admitted_knowledge_scope,
            )

        try:
            async with goal_thread_lock(thread_id):
                await ensure_checkpoint_history_seeded(
                    request,
                    thread_id=thread_id,
                    assistant_id=body.assistant_id,
                )
                # A strict caller may have observed the thread before a
                # concurrent delete removed it while checkpoint preparation
                # yielded. Recheck immediately before durable admission. The
                # delete route holds a durable thread-operation reservation,
                # so after this point either the run or the delete wins; they
                # cannot both succeed across Gateway workers.
                if require_existing_thread and not await thread_access_allowed():
                    raise HTTPException(status_code=404, detail=f"Thread {thread_id} not found")
                record = await run_mgr.create_or_reject(
                    thread_id,
                    body.assistant_id,
                    on_disconnect=disconnect,
                    metadata=run_metadata,
                    # Persist a secret-redacted copy of the config: the run record is
                    # written to runs.kwargs_json and echoed by the run API, so a
                    # request-scoped secret (#3861) must not ride along. The live
                    # config built above keeps the secrets for the actual run.
                    kwargs={
                        "input": run_record_input,
                        "config": redact_config_secrets(body.config),
                        **({"conversation_references": conversation_references} if conversation_references else {}),
                    },
                    multitask_strategy=body.multitask_strategy,
                    model_name=model_name,
                    user_id=owner_user_id,
                    idempotency_key=idempotency_key,
                )

                if record.idempotency_reused:
                    stored = record.kwargs or {}
                    stored_input = stored.get("input")
                    # New runs persist the admitted, canonical message snapshot
                    # so a scope display cannot be rewritten through the run
                    # record. Accept the raw request as well for records written
                    # by older Gateway versions, while comparing canonical
                    # retries to the same representation as the stored record.
                    if (stored_input != body.input and stored_input != run_record_input) or record.assistant_id != body.assistant_id or stored.get("conversation_references", []) != conversation_references:
                        raise HTTPException(
                            status_code=409,
                            detail="Idempotency-Key already used with a different request",
                        )
                    return record

                worker = run_after_metadata(record)
                try:
                    # No await is allowed between durable admission and task
                    # attachment. Metadata setup runs inside the attached
                    # worker so a pending cancellation can bypass stalled
                    # thread-store IO and still reach run_agent's startup
                    # barrier / stream finalization.
                    record.task = asyncio.create_task(worker)
                except Exception as exc:
                    worker.close()
                    await run_mgr.fail_start_if_pending(
                        record.run_id,
                        error=f"Failed to attach run worker: {exc}",
                    )
                    raise
        except ConflictError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        except UnsupportedStrategyError as exc:
            raise HTTPException(status_code=501, detail=str(exc)) from exc

        # Title sync is handled by worker.py's finally block which reads the
        # title from the checkpoint and calls thread_store.update_display_name
        # after the run completes.

        return record
    finally:
        if owner_context_token is not None:
            reset_current_user(owner_context_token)
