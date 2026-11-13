import pytest

from automotive_data_integration.pipeline_api.repository import PostgresRepository


@pytest.mark.parametrize("status", ["running", "unknown"])
def test_finish_pipeline_run_rejects_nonterminal_status_before_connecting(status):
    repository = PostgresRepository(
        "postgresql://nobody:nobody@127.0.0.1:1/unreachable?connect_timeout=1"
    )

    with pytest.raises(ValueError, match="status"):
        repository.finish_pipeline_run(
            1,
            status=status,
            fetched_count=0,
            accepted_count=0,
            rejected_count=0,
            duplicate_count=0,
        )
