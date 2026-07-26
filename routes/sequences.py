from typing import Any, Dict, Optional

from fastapi import APIRouter, Body, Depends, File, HTTPException, Response, UploadFile
from pydantic import BaseModel, ConfigDict, Field

from observatory.error_handler import handle_error
from observatory.observatory import Observatory
from observatory.sequence_parser import SequenceParser
from routes import get_observatory


class StartSequenceRequest(BaseModel):
    params: Dict[str, Any] = Field(default_factory=dict)
    model_config = ConfigDict(extra="forbid")


router = APIRouter(prefix="/sequences", tags=["sequences"])


@router.get("")
async def list_sequences(observatory: Observatory = Depends(get_observatory)):
    return {"sequences": observatory.sequence_registry.list_sequences()}


@router.get("/active")
async def list_active_sequences(observatory: Observatory = Depends(get_observatory)):
    return {
        "active_sequences": [
            sequence.model_dump()
            for sequence in observatory.state.snapshot().sequences.values()
        ]
    }


@router.post("/parse")
async def upload_sequence(
    file: UploadFile = File(...),
    dry_run: bool = False,
    save: bool = False,
    observatory: Observatory = Depends(get_observatory),
):
    if not file.filename or not file.filename.endswith((".yaml", ".yml")):
        raise HTTPException(
            status_code=400,
            detail="Invalid file type. Please upload a YAML file.",
        )

    content = await file.read()
    try:
        yaml_string = content.decode("utf-8")
        parsed_builder = SequenceParser(
            yaml_string,
            observatory,
            filename=file.filename,
        )
        parsed_sequence = parsed_builder.build(save=save)
        print(parsed_sequence)
        if dry_run:
            return {"status": "valid", "parsed_steps": len(parsed_sequence.steps)}

        observatory.sequence_registry.add_sequence(parsed_builder)
        return {"status": "parsed"}
    except Exception as e:
        message = handle_error(e, "Failed to parse sequence", level="error")
        raise HTTPException(status_code=400, detail=message)


@router.post("/refresh")
async def refresh_sequence_catalog(
    observatory: Observatory = Depends(get_observatory),
):
    observatory.refresh_sequence_catalog()
    return {"sequences": observatory.sequence_registry.list_sequences()}


@router.get("/{sequence_id}", response_class=Response)
async def get_sequence_yaml(
    sequence_id: str,
    observatory: Observatory = Depends(get_observatory),
):
    sequence_builder = observatory.sequence_registry.sequences.get(sequence_id)
    if sequence_builder is None:
        raise HTTPException(
            status_code=404,
            detail=f"Sequence '{sequence_id}' not found.",
        )

    yaml_string = getattr(sequence_builder, "yaml_string", None)
    if yaml_string is None:
        raise HTTPException(
            status_code=404,
            detail=f"YAML for sequence '{sequence_id}' is not available.",
        )

    return Response(content=yaml_string, media_type="application/yaml")


@router.post("/{sequence_id}/run")
async def run_sequence(
    sequence_id: str,
    observatory: Observatory = Depends(get_observatory),
    body: Optional[StartSequenceRequest] = Body(None),
):
    sequence_builder = observatory.sequence_registry.sequences.get(sequence_id)
    if sequence_builder is None:
        raise HTTPException(
            status_code=404,
            detail=f"Sequence '{sequence_id}' not found.",
        )

    params = body.params if body else {}
    context_id = observatory.sequence_registry.run_sequence(
        observatory,
        sequence_builder,
        **params,
    )
    return {"context_id": context_id}


def _get_sequence_context(context_id: str, observatory: Observatory):
    context_entry = observatory.sequence_registry.registry.get(context_id)
    if context_entry is None:
        raise HTTPException(
            status_code=404,
            detail=f"Sequence with context_id '{context_id}' not found.",
        )
    return context_entry[1]


@router.post("/{context_id}/pause")
async def pause_sequence(
    context_id: str,
    observatory: Observatory = Depends(get_observatory),
):
    context = _get_sequence_context(context_id, observatory)
    context.request_pause()
    observatory.state.set_sequence_status(context_id, "paused")
    return {"status": "paused"}


@router.post("/{context_id}/resume")
async def resume_sequence(
    context_id: str,
    observatory: Observatory = Depends(get_observatory),
):
    context = _get_sequence_context(context_id, observatory)
    context.resume()
    observatory.state.set_sequence_status(context_id, "running")
    return {"status": "resumed"}


@router.post("/{context_id}/abort")
async def abort_sequence(
    context_id: str,
    observatory: Observatory = Depends(get_observatory),
):
    context = _get_sequence_context(context_id, observatory)
    context.abort()
    observatory.state.set_sequence_status(context_id, "aborting")
    return {"status": "aborted"}
