from pathlib import Path


def test_docker_compose_defines_required_services() -> None:
    here = Path(__file__).resolve()
    compose_path = None
    # Prefer an explicitly mounted compose file (Docker test environment), then walk up.
    candidates = [here.parent / "docker-compose.yml", Path("/app/docker-compose.yml")]
    candidates.extend(parent / "docker-compose.yml" for parent in here.parents)
    for candidate in candidates:
        if candidate.is_file():
            compose_path = candidate
            break
    assert compose_path is not None, (
        "docker-compose.yml must be available for this contract test "
        "(mounted at /app/docker-compose.yml in Docker, or present in a parent directory)."
    )
    content = compose_path.read_text(encoding="utf-8")
    assert "postgres:" in content
    assert "api:" in content
    assert "web:" in content
    assert "healthcheck:" in content
    assert "OCR_TEMP_DIR" in content
    assert "OCR_EXECUTABLE" in content
    assert "127.0.0.1:8000:8000" in content
    assert "127.0.0.1:3000:3000" in content
    assert "no-new-privileges:true" in content
    assert "ALLOWED_HOSTS" in content
    assert "MAX_CONCURRENT_OCR_JOBS" in content
    # Postgres must not be published on the host for local MVP.
    assert '"5432:5432"' not in content
    assert "5432:5432" not in content
