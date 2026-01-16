"""
Tests for Strategy Generation API Routes

Tests the strategy generation job management and suggestion review endpoints.
"""

import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from uuid import uuid4
from datetime import datetime

# Test data fixtures
@pytest.fixture
def mock_client():
    return {
        "id": str(uuid4()),
        "name": "Test Client",
        "workspace_id": str(uuid4()),
    }

@pytest.fixture
def mock_job(mock_client):
    return {
        "id": str(uuid4()),
        "client_id": mock_client["id"],
        "submission_id": None,
        "status": "pending",
        "generation_round": 1,
        "error_message": None,
        "created_at": datetime.now(),
        "started_at": None,
        "completed_at": None,
    }

@pytest.fixture
def mock_suggestion(mock_job, mock_client):
    return {
        "id": str(uuid4()),
        "job_id": mock_job["id"],
        "client_id": mock_client["id"],
        "variant_number": 1,
        "subject_line": "Quick q about {{company_name}}",
        "email_body": "Hey {{first_name}},\n\nNoticed you...",
        "score": 87,
        "rationale": "Strong custom signal opening",
        "used_variables": ["{{first_name}}", "{{company_name}}"],
        "campaign_type": "custom_signal",
        "status": "pending",
        "human_comment": None,
        "reviewed_by": None,
        "reviewed_at": None,
        "generation_round": 1,
        "created_at": datetime.now(),
    }


class TestStrategyJobCreation:
    """Tests for POST /api/strategy/jobs/{client_id}"""

    @pytest.mark.asyncio
    async def test_create_job_success(self, mock_client):
        """Should create a new strategy generation job"""
        from routes.strategy import create_strategy_job
        from models.strategy import StrategyJobCreate

        client_id = uuid4()
        mock_job_response = {
            "id": uuid4(),
            "status": "pending",
            "generation_round": 1,
            "created_at": datetime.now(),
        }

        with patch('routes.strategy.fetch_one') as mock_fetch:
            # Mock client exists
            mock_fetch.side_effect = [
                {"id": str(client_id), "name": "Test Client", "workspace_id": str(uuid4())},
                None,  # No previous job
                mock_job_response,  # New job created
            ]

            result = await create_strategy_job(client_id, None)

            assert result["status"] == "pending"
            assert result["generation_round"] == 1
            assert "job_id" in result

    @pytest.mark.asyncio
    async def test_create_job_client_not_found(self):
        """Should return 404 if client doesn't exist"""
        from routes.strategy import create_strategy_job
        from fastapi import HTTPException

        client_id = uuid4()

        with patch('routes.strategy.fetch_one', return_value=None):
            with pytest.raises(HTTPException) as exc_info:
                await create_strategy_job(client_id, None)

            assert exc_info.value.status_code == 404
            assert "Client not found" in str(exc_info.value.detail)

    @pytest.mark.asyncio
    async def test_create_job_increments_generation_round(self, mock_client):
        """Should increment generation round from previous job"""
        from routes.strategy import create_strategy_job

        client_id = uuid4()

        with patch('routes.strategy.fetch_one') as mock_fetch:
            mock_fetch.side_effect = [
                mock_client,  # Client exists
                {"generation_round": 3},  # Previous job was round 3
                {"id": uuid4(), "status": "pending", "generation_round": 4, "created_at": datetime.now()},
            ]

            result = await create_strategy_job(client_id, None)

            assert result["generation_round"] == 4


class TestStrategyJobStatus:
    """Tests for GET /api/strategy/jobs/{job_id}/status"""

    @pytest.mark.asyncio
    async def test_get_job_status_success(self, mock_job):
        """Should return job status"""
        from routes.strategy import get_job_status

        job_id = uuid4()
        mock_job["client_name"] = "Test Client"

        with patch('routes.strategy.fetch_one', return_value=mock_job):
            result = await get_job_status(job_id)

            assert result.status == "pending"
            assert result.generation_round == 1

    @pytest.mark.asyncio
    async def test_get_job_status_not_found(self):
        """Should return 404 if job doesn't exist"""
        from routes.strategy import get_job_status
        from fastapi import HTTPException

        job_id = uuid4()

        with patch('routes.strategy.fetch_one', return_value=None):
            with pytest.raises(HTTPException) as exc_info:
                await get_job_status(job_id)

            assert exc_info.value.status_code == 404


class TestStrategySuggestions:
    """Tests for GET /api/strategy/suggestions/{client_id}"""

    @pytest.mark.asyncio
    async def test_get_client_suggestions(self, mock_suggestion):
        """Should return suggestions for a client"""
        from routes.strategy import get_client_suggestions

        client_id = uuid4()
        mock_suggestion["job_round"] = 1

        with patch('routes.strategy.fetch_all', return_value=[mock_suggestion]):
            with patch('routes.strategy.fetch_one', return_value={
                "pending_count": 1,
                "approved_count": 0,
                "denied_count": 0,
                "revision_count": 0,
                "total": 1,
            }):
                result = await get_client_suggestions(client_id)

                assert result.total == 1
                assert result.pending_count == 1
                assert len(result.suggestions) == 1

    @pytest.mark.asyncio
    async def test_get_suggestions_with_status_filter(self, mock_suggestion):
        """Should filter suggestions by status"""
        from routes.strategy import get_client_suggestions

        client_id = uuid4()
        mock_suggestion["job_round"] = 1
        mock_suggestion["status"] = "approved"

        with patch('routes.strategy.fetch_all', return_value=[mock_suggestion]):
            with patch('routes.strategy.fetch_one', return_value={
                "pending_count": 0,
                "approved_count": 1,
                "denied_count": 0,
                "revision_count": 0,
                "total": 1,
            }):
                result = await get_client_suggestions(client_id, status="approved")

                assert result.approved_count == 1


class TestSuggestionReview:
    """Tests for POST /api/strategy/suggestions/{suggestion_id}/review"""

    @pytest.mark.asyncio
    async def test_approve_suggestion(self, mock_suggestion):
        """Should approve a suggestion"""
        from routes.strategy import review_suggestion
        from models.strategy import SuggestionReviewRequest

        suggestion_id = uuid4()
        request = SuggestionReviewRequest(action="approve", comment="Great variant!")

        with patch('routes.strategy.fetch_one', return_value=mock_suggestion):
            with patch('routes.strategy.execute', new_callable=AsyncMock):
                result = await review_suggestion(suggestion_id, request)

                assert result["status"] == "approved"

    @pytest.mark.asyncio
    async def test_deny_suggestion(self, mock_suggestion):
        """Should deny a suggestion"""
        from routes.strategy import review_suggestion
        from models.strategy import SuggestionReviewRequest

        suggestion_id = uuid4()
        request = SuggestionReviewRequest(action="deny", comment="Too generic")

        with patch('routes.strategy.fetch_one', return_value=mock_suggestion):
            with patch('routes.strategy.execute', new_callable=AsyncMock):
                result = await review_suggestion(suggestion_id, request)

                assert result["status"] == "denied"

    @pytest.mark.asyncio
    async def test_request_revision(self, mock_suggestion):
        """Should request revision for a suggestion"""
        from routes.strategy import review_suggestion
        from models.strategy import SuggestionReviewRequest

        suggestion_id = uuid4()
        request = SuggestionReviewRequest(
            action="revision_requested",
            comment="Make it shorter"
        )

        with patch('routes.strategy.fetch_one', return_value=mock_suggestion):
            with patch('routes.strategy.execute', new_callable=AsyncMock):
                result = await review_suggestion(suggestion_id, request)

                assert result["status"] == "revision_requested"

    @pytest.mark.asyncio
    async def test_review_invalid_action(self, mock_suggestion):
        """Should reject invalid review action"""
        from routes.strategy import review_suggestion
        from models.strategy import SuggestionReviewRequest
        from fastapi import HTTPException

        suggestion_id = uuid4()
        request = SuggestionReviewRequest(action="invalid_action")

        with patch('routes.strategy.fetch_one', return_value=mock_suggestion):
            with pytest.raises(HTTPException) as exc_info:
                await review_suggestion(suggestion_id, request)

            assert exc_info.value.status_code == 400

    @pytest.mark.asyncio
    async def test_review_suggestion_not_found(self):
        """Should return 404 if suggestion doesn't exist"""
        from routes.strategy import review_suggestion
        from models.strategy import SuggestionReviewRequest
        from fastapi import HTTPException

        suggestion_id = uuid4()
        request = SuggestionReviewRequest(action="approve")

        with patch('routes.strategy.fetch_one', return_value=None):
            with pytest.raises(HTTPException) as exc_info:
                await review_suggestion(suggestion_id, request)

            assert exc_info.value.status_code == 404


class TestRevisionRequests:
    """Tests for revision request endpoints"""

    @pytest.mark.asyncio
    async def test_create_revision_request(self, mock_suggestion):
        """Should create a revision request"""
        from routes.strategy import request_revision
        from models.strategy import RevisionRequestCreate

        suggestion_id = uuid4()
        request = RevisionRequestCreate(instruction="Make it shorter and punchier")

        mock_suggestion_with_ids = {
            **mock_suggestion,
            "job_id": uuid4(),
            "client_id": uuid4(),
        }

        with patch('routes.strategy.fetch_one') as mock_fetch:
            mock_fetch.side_effect = [
                mock_suggestion_with_ids,  # Get suggestion
                {"id": uuid4(), "created_at": datetime.now()},  # Insert revision
            ]
            with patch('routes.strategy.execute', new_callable=AsyncMock):
                result = await request_revision(suggestion_id, request)

                assert result.instruction == "Make it shorter and punchier"
                assert result.processed == False

    @pytest.mark.asyncio
    async def test_get_client_revisions(self):
        """Should get revision requests for a client"""
        from routes.strategy import get_client_revisions

        client_id = uuid4()
        mock_revisions = [
            {
                "id": str(uuid4()),
                "job_id": str(uuid4()),
                "variant_id": str(uuid4()),
                "subject_line": "Test subject",
                "instruction": "Make it shorter",
                "processed": False,
                "created_at": datetime.now(),
            }
        ]

        with patch('routes.strategy.fetch_all', return_value=mock_revisions):
            result = await get_client_revisions(client_id)

            assert result["total"] == 1
            assert len(result["revisions"]) == 1


class TestStrategyModels:
    """Tests for Pydantic models"""

    def test_strategy_job_create_optional_submission(self):
        """StrategyJobCreate should allow optional submission_id"""
        from models.strategy import StrategyJobCreate

        # Without submission_id
        job1 = StrategyJobCreate()
        assert job1.submission_id is None

        # With submission_id
        submission_id = uuid4()
        job2 = StrategyJobCreate(submission_id=submission_id)
        assert job2.submission_id == submission_id

    def test_suggestion_review_request_validation(self):
        """SuggestionReviewRequest should validate action"""
        from models.strategy import SuggestionReviewRequest

        # Valid actions
        for action in ['approve', 'deny', 'revision_requested']:
            request = SuggestionReviewRequest(action=action)
            assert request.action == action

    def test_revision_request_create(self):
        """RevisionRequestCreate should require instruction"""
        from models.strategy import RevisionRequestCreate

        request = RevisionRequestCreate(instruction="Make it shorter")
        assert request.instruction == "Make it shorter"


# Integration-style tests (would need actual DB connection)
class TestStrategyIntegration:
    """Integration tests that would run against a test database"""

    @pytest.mark.skip(reason="Requires database connection")
    @pytest.mark.asyncio
    async def test_full_workflow(self):
        """Test complete workflow: create job -> save suggestions -> review"""
        pass

    @pytest.mark.skip(reason="Requires database connection")
    @pytest.mark.asyncio
    async def test_generation_round_tracking(self):
        """Test that generation rounds increment correctly across jobs"""
        pass
