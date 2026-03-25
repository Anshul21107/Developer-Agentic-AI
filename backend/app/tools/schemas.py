"""Pydantic input schemas for all chatbot tools."""

from pydantic import BaseModel, Field


class GetWeatherInput(BaseModel):
    """Get current weather for a location."""

    location: str = Field(description="City or place name to get weather for")


class QueryRagInput(BaseModel):
    """Query uploaded documents for relevant information."""

    query: str = Field(description="The search query to find relevant document chunks")


class SearchWebInput(BaseModel):
    """Search the web for up-to-date information."""

    query: str = Field(description="The search query")
    max_results: int = Field(default=5, description="Maximum number of results to return")


class FetchNewsInput(BaseModel):
    """Fetch latest news headlines, optionally filtered by topic."""

    query: str | None = Field(
        default=None,
        description="Optional topic to filter news. If None, returns top headlines.",
    )


class DraftEmailInput(BaseModel):
    """Draft a new email based on user instructions."""

    to: str = Field(description="Recipient email address")
    subject: str = Field(description="A clear, descriptive email subject line")
    body: str = Field(
        description="Complete email body with proper formatting: greeting, "
        "well-structured content, and a professional sign-off (e.g. Regards). "
        "Do not pass raw data — compose a readable email."
    )


class EditEmailInput(BaseModel):
    """Edit specific fields of the pending email draft. Pass only the fields you want to change."""

    to: str | None = Field(default=None, description="New recipient email address")
    subject: str | None = Field(default=None, description="New subject line")
    body: str | None = Field(default=None, description="New email body")


class SendEmailInput(BaseModel):
    """Send the pending email draft in the current session."""
    pass


class CancelEmailInput(BaseModel):
    """Cancel and discard the pending email draft in the current session."""
    pass
