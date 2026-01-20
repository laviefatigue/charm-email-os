"""Simple test flow to verify Prefect worker is working."""
from prefect import flow

@flow(name="test-flow")
def test_flow(message: str = "Hello from Prefect!"):
    """Simple test flow."""
    print(f"Test flow running: {message}")
    return {"status": "success", "message": message}

if __name__ == "__main__":
    result = test_flow()
    print(f"Result: {result}")
