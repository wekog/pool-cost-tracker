from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

import httpx

from .settings import Settings


class PaperlessError(RuntimeError):
    pass


class PaperlessClient:
    def __init__(self, settings: Settings):
        self.settings = settings

    def _headers(self) -> dict[str, str]:
        return {'Authorization': f'Token {self.settings.PAPERLESS_TOKEN}'}

    def _url(self, path: str) -> str:
        return f"{self.settings.PAPERLESS_BASE_URL.rstrip('/')}{path}"

    def _to_path(self, url_or_path: str) -> str:
        base = self.settings.PAPERLESS_BASE_URL.rstrip('/')
        if url_or_path.startswith(base):
            return url_or_path.replace(base, '', 1)
        return url_or_path

    async def _get_page(self, client: httpx.AsyncClient, path: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        response = await client.get(self._url(path), headers=self._headers(), params=params, timeout=30.0)
        response.raise_for_status()
        payload = response.json()
        if not isinstance(payload, dict):
            raise PaperlessError('Unerwartetes API-Format von Paperless')
        return payload

    async def probe(self) -> int:
        start = datetime.now(timezone.utc)
        async with httpx.AsyncClient() as client:
            response = await client.get(
                self._url('/api/tags/'),
                headers=self._headers(),
                params={'page_size': 1},
                timeout=5.0,
            )
            response.raise_for_status()
        elapsed = datetime.now(timezone.utc) - start
        return int(elapsed.total_seconds() * 1000)

    async def get_tag_id_by_name(self) -> int:
        async with httpx.AsyncClient() as client:
            next_path = '/api/tags/'
            while next_path:
                page = await self._get_page(client, self._to_path(next_path))
                for tag in page.get('results', []):
                    if tag.get('name') == self.settings.PROJECT_TAG_NAME:
                        return int(tag['id'])
                next_path = self._to_path(page['next']) if page.get('next') else ''
        raise PaperlessError(f"Tag '{self.settings.PROJECT_TAG_NAME}' nicht gefunden")

    async def get_project_documents(self, project_tag_id: int) -> list[dict[str, Any]]:
        documents: list[dict[str, Any]] = []
        cutoff = datetime.now(timezone.utc) - timedelta(days=self.settings.SYNC_LOOKBACK_DAYS)
        params: dict[str, Any] | None = {
            'tags__id': project_tag_id,
            'page_size': self.settings.SYNC_PAGE_SIZE,
            'ordering': '-created',
            'truncate_content': 'false',
        }

        async with httpx.AsyncClient() as client:
            next_path = '/api/documents/'
            while next_path:
                page = await self._get_page(client, self._to_path(next_path), params=params)
                params = None
                for item in page.get('results', []):
                    created = item.get('created')
                    if created:
                        try:
                            created_dt = datetime.fromisoformat(created.replace('Z', '+00:00'))
                            if created_dt.tzinfo is None:
                                created_dt = created_dt.replace(tzinfo=timezone.utc)
                            if created_dt < cutoff:
                                return documents
                        except ValueError:
                            pass
                    documents.append(self._normalize_document(item))
                next_path = self._to_path(page['next']) if page.get('next') else ''
        return documents

    def _normalize_document(self, item: dict[str, Any]) -> dict[str, Any]:
        correspondent_obj = item.get('correspondent')
        if isinstance(correspondent_obj, dict):
            correspondent_name = correspondent_obj.get('name')
        else:
            correspondent_name = correspondent_obj

        document_type_obj = item.get('document_type')
        if isinstance(document_type_obj, dict):
            document_type = document_type_obj.get('name')
        else:
            document_type = document_type_obj

        tags = item.get('tags') or []
        normalized_tags = []
        for tag in tags:
            if isinstance(tag, dict):
                normalized_tags.append({'id': tag.get('id'), 'name': tag.get('name')})
            else:
                normalized_tags.append({'id': tag, 'name': None})

        return {
            'id': item.get('id'),
            'title': item.get('title'),
            'created': item.get('created'),
            'correspondent': correspondent_name,
            'content': item.get('content') or '',
            'tags': normalized_tags,
            'document_type': document_type,
        }
