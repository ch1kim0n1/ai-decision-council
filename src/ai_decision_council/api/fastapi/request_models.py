"""Pydantic request models for the FastAPI integration."""

from __future__ import annotations

from pydantic import BaseModel, Field


class SendMessageRequest(BaseModel):
    """Request to send a user message through the council pipeline."""

    content: str = Field(min_length=1)


