"""Chat model settings API for the local workspace."""

from fastapi import APIRouter, HTTPException, Request, Response
from fastapi.exceptions import RequestValidationError
from fastapi.routing import APIRoute
from pydantic import BaseModel

from src.llm.settings import (
    CredentialSource,
    ModelSelections,
    ModelSettings,
    ModelSettingsUnavailableError,
    get_model_settings,
    save_model_settings,
)


class ModelSettingsRoute(APIRoute):
    def get_route_handler(self):
        handler = super().get_route_handler()

        async def handle(request: Request) -> Response:
            if request.method == "PUT" and request.headers.get("origin") not in (
                None,
                f"{request.url.scheme}://{request.url.netloc}",
            ):
                raise HTTPException(403, "请从工作台页面保存模型配置。")
            try:
                response = await handler(request)
            except RequestValidationError:
                # The default validation response echoes submitted values.
                raise HTTPException(422, "请检查模型配置和 API Key 格式。") from None
            except ModelSettingsUnavailableError as exc:
                raise HTTPException(503, str(exc)) from None
            response.headers["Cache-Control"] = "no-store"
            return response

        return handle


router = APIRouter(route_class=ModelSettingsRoute)


class CredentialsResponse(BaseModel):
    deepseek: CredentialSource
    bailian: CredentialSource


class ModelSettingsResponse(ModelSelections):
    credentials: CredentialsResponse


def _public_settings(settings: ModelSettings) -> ModelSettingsResponse:
    return ModelSettingsResponse(
        **settings.model_dump(),
        credentials=CredentialsResponse(
            deepseek=settings.credential_source("deepseek"),
            bailian=settings.credential_source("bailian"),
        ),
    )


@router.get("/model-settings")
async def read_settings() -> ModelSettingsResponse:
    return _public_settings(await get_model_settings())


@router.put("/model-settings")
async def update_settings(settings: ModelSettings) -> ModelSettingsResponse:
    return _public_settings(await save_model_settings(settings))
