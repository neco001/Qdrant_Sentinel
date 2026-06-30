"""Unit tests for embedding_service module."""

import pytest
from unittest.mock import MagicMock, patch, PropertyMock

from embedding_service.base import EmbeddingService
from embedding_service.openai_compatible import OpenAICompatibleService
from embedding_service.byteplus_ark import BytePlusArkService
from embedding_service.factory import EmbeddingServiceFactory


class TestEmbeddingServiceFactory:
    """Tests for EmbeddingServiceFactory."""

    def test_create_openai_compatible(self):
        """Factory should create OpenAICompatibleService for 'openai_compatible' provider."""
        with patch("embedding_service.openai_compatible.OpenAI"):
            service = EmbeddingServiceFactory.create(
                provider="openai_compatible",
                api_key="test-key",
                model_name="text-embedding-v4",
                base_url="https://example.com/v1",
                vector_size=1024,
            )
        assert isinstance(service, OpenAICompatibleService)

    def test_create_byteplus_ark(self):
        """Factory should create BytePlusArkService for 'byteplus_ark' provider."""
        with patch("embedding_service.openai_compatible.OpenAI"):
            service = EmbeddingServiceFactory.create(
                provider="byteplus_ark",
                api_key="test-key",
                model_name="my-endpoint",
            )
        assert isinstance(service, BytePlusArkService)

    def test_create_with_alias_alibaba(self):
        """Factory should support 'alibaba' alias."""
        with patch("embedding_service.openai_compatible.OpenAI"):
            service = EmbeddingServiceFactory.create(
                provider="alibaba",
                api_key="test-key",
                model_name="text-embedding-v4",
            )
        assert isinstance(service, OpenAICompatibleService)

    def test_create_with_alias_dashscope(self):
        """Factory should support 'dashscope' alias."""
        with patch("embedding_service.openai_compatible.OpenAI"):
            service = EmbeddingServiceFactory.create(
                provider="dashscope",
                api_key="test-key",
                model_name="text-embedding-v4",
            )
        assert isinstance(service, OpenAICompatibleService)

    def test_create_with_alias_byteplus(self):
        """Factory should support 'byteplus' alias."""
        with patch("embedding_service.openai_compatible.OpenAI"):
            service = EmbeddingServiceFactory.create(
                provider="byteplus",
                api_key="test-key",
                model_name="my-endpoint",
            )
        assert isinstance(service, BytePlusArkService)

    def test_create_unknown_provider_raises_error(self):
        """Factory should raise ValueError for unknown provider."""
        with pytest.raises(ValueError, match="Unknown embedding provider"):
            EmbeddingServiceFactory.create(
                provider="unknown_provider",
                api_key="test-key",
                model_name="model",
            )

    def test_get_supported_providers(self):
        """Factory should return list of supported provider names."""
        providers = EmbeddingServiceFactory.get_supported_providers()
        assert "openai_compatible" in providers
        assert "byteplus_ark" in providers
        assert "alibaba" in providers
        assert "dashscope" in providers
        assert "byteplus" in providers

    def test_get_provider_defaults(self):
        """Factory should return default config for known provider."""
        defaults = EmbeddingServiceFactory.get_provider_defaults("openai_compatible")
        assert "base_url" in defaults
        assert "vector_size" in defaults

    def test_get_provider_defaults_unknown_raises(self):
        """Factory should raise ValueError for unknown provider defaults."""
        with pytest.raises(ValueError, match="Unknown provider"):
            EmbeddingServiceFactory.get_provider_defaults("nonexistent")


class TestOpenAICompatibleService:
    """Tests for OpenAICompatibleService."""

    @pytest.fixture
    def mock_openai_client(self):
        """Create a mocked OpenAI client."""
        with patch("embedding_service.openai_compatible.OpenAI") as MockOpenAI:
            mock_client = MagicMock()
            MockOpenAI.return_value = mock_client
            yield mock_client, MockOpenAI

    def test_init_with_required_params(self, mock_openai_client):
        """Should initialize with api_key and model_name."""
        mock_client, MockOpenAI = mock_openai_client
        service = OpenAICompatibleService(
            api_key="test-key",
            model_name="text-embedding-v4",
            base_url="https://example.com/v1",
            vector_size=1024,
        )
        MockOpenAI.assert_called_once_with(
            api_key="test-key",
            base_url="https://example.com/v1",
        )
        assert service.vector_size == 1024

    def test_init_without_model_name_raises(self, mock_openai_client):
        """Should raise ValueError if model_name is not provided."""
        with pytest.raises(ValueError, match="model_name is required"):
            OpenAICompatibleService(
                api_key="test-key",
                model_name=None,
                base_url="https://example.com/v1",
            )

    def test_embed_single_text(self, mock_openai_client):
        """Should call API with single text and return embedding."""
        mock_client, _ = mock_openai_client
        mock_response = MagicMock()
        mock_response.data = [MagicMock(embedding=[0.1, 0.2, 0.3])]
        mock_client.embeddings.create.return_value = mock_response

        service = OpenAICompatibleService(
            api_key="test-key",
            model_name="text-embedding-v4",
            vector_size=3,
        )
        result = service.embed("Hello world")

        mock_client.embeddings.create.assert_called_once_with(
            input=["Hello world"],
            model="text-embedding-v4",
        )
        assert result == [0.1, 0.2, 0.3]

    def test_embed_batch_texts(self, mock_openai_client):
        """Should call API with batch texts and return embeddings."""
        mock_client, _ = mock_openai_client
        mock_response = MagicMock()
        mock_response.data = [
            MagicMock(index=0, embedding=[0.1, 0.2]),
            MagicMock(index=1, embedding=[0.3, 0.4]),
        ]
        mock_client.embeddings.create.return_value = mock_response

        service = OpenAICompatibleService(
            api_key="test-key",
            model_name="text-embedding-v4",
            vector_size=2,
        )
        result = service.embed_batch(["text1", "text2"])

        mock_client.embeddings.create.assert_called_once_with(
            input=["text1", "text2"],
            model="text-embedding-v4",
        )
        assert result == [[0.1, 0.2], [0.3, 0.4]]

    def test_embed_query_alias(self, mock_openai_client):
        """embed_query should delegate to embed."""
        mock_client, _ = mock_openai_client
        mock_response = MagicMock()
        mock_response.data = [MagicMock(embedding=[0.1, 0.2, 0.3])]
        mock_client.embeddings.create.return_value = mock_response

        service = OpenAICompatibleService(
            api_key="test-key",
            model_name="text-embedding-v4",
            vector_size=3,
        )
        result = service.embed_query("query text")

        assert result == [0.1, 0.2, 0.3]

    def test_embed_documents_alias(self, mock_openai_client):
        """embed_documents should delegate to embed_batch."""
        mock_client, _ = mock_openai_client
        mock_response = MagicMock()
        mock_response.data = [
            MagicMock(index=0, embedding=[0.1]),
            MagicMock(index=1, embedding=[0.2]),
        ]
        mock_client.embeddings.create.return_value = mock_response

        service = OpenAICompatibleService(
            api_key="test-key",
            model_name="text-embedding-v4",
            vector_size=1,
        )
        result = service.embed_documents(["doc1", "doc2"])

        assert result == [[0.1], [0.2]]


class TestBytePlusArkService:
    """Tests for BytePlusArkService."""

    @pytest.fixture
    def mock_openai_service(self):
        """Create a mocked OpenAICompatibleService."""
        with patch("embedding_service.byteplus_ark.OpenAICompatibleService") as MockService:
            mock_impl = MagicMock()
            mock_impl.vector_size = 1024
            mock_impl.embed.return_value = [0.1, 0.2]
            mock_impl.embed_batch.return_value = [[0.1], [0.2]]
            mock_impl._client = MagicMock()
            MockService.return_value = mock_impl
            yield mock_impl, MockService

    def test_init_uses_default_base_url(self, mock_openai_service):
        """Should use BytePlus default base URL when not specified."""
        mock_impl, MockService = mock_openai_service
        service = BytePlusArkService(
            api_key="byteplus-key",
            model_name="my-endpoint",
        )
        MockService.assert_called_once_with(
            api_key="byteplus-key",
            model_name="my-endpoint",
            base_url=BytePlusArkService.DEFAULT_BASE_URL,
            vector_size=BytePlusArkService.DEFAULT_VECTOR_SIZE,
        )

    def test_init_with_custom_base_url(self, mock_openai_service):
        """Should use custom base URL when provided."""
        mock_impl, MockService = mock_openai_service
        service = BytePlusArkService(
            api_key="byteplus-key",
            model_name="my-endpoint",
            base_url="https://custom.byteplus.com/v1",
        )
        MockService.assert_called_once_with(
            api_key="byteplus-key",
            model_name="my-endpoint",
            base_url="https://custom.byteplus.com/v1",
            vector_size=BytePlusArkService.DEFAULT_VECTOR_SIZE,
        )

    def test_vector_size_property(self, mock_openai_service):
        """Should return vector_size from impl."""
        mock_impl, _ = mock_openai_service
        service = BytePlusArkService(
            api_key="byteplus-key",
            model_name="my-endpoint",
        )
        assert service.vector_size == 1024

    def test_embed_delegates_to_impl(self, mock_openai_service):
        """Should delegate embed to impl."""
        mock_impl, _ = mock_openai_service
        service = BytePlusArkService(
            api_key="byteplus-key",
            model_name="my-endpoint",
        )
        result = service.embed("text")
        mock_impl.embed.assert_called_once_with("text")
        assert result == [0.1, 0.2]

    def test_embed_batch_delegates_to_impl(self, mock_openai_service):
        """Should delegate embed_batch to impl."""
        mock_impl, _ = mock_openai_service
        service = BytePlusArkService(
            api_key="byteplus-key",
            model_name="my-endpoint",
        )
        result = service.embed_batch(["text1", "text2"])
        mock_impl.embed_batch.assert_called_once_with(["text1", "text2"])
        assert result == [[0.1], [0.2]]

    def test_client_property(self, mock_openai_service):
        """Should expose underlying OpenAI client."""
        mock_impl, _ = mock_openai_service
        service = BytePlusArkService(
            api_key="byteplus-key",
            model_name="my-endpoint",
        )
        assert service.client == mock_impl._client


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
