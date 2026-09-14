import httpx

from librarian.sabnzbd import SABClient, SABError, map_sab_status


def test_map_sab_status_values():
    assert map_sab_status("Downloading") == "downloading"
    assert map_sab_status("Extracting") == "extracting"
    assert map_sab_status("Completed", history=True) == "completed"
    assert map_sab_status("Failed", history=True) == "failed"
    assert map_sab_status("Queued") == "queued"


def test_addurl_and_job_status_nzo_id():
    def handler(request: httpx.Request) -> httpx.Response:
        params = dict(request.url.params)
        if params.get("mode") == "addurl":
            return httpx.Response(200, json={"status": True, "nzo_ids": ["SABnzbd_nzo_abc"]})
        if params.get("mode") == "queue":
            return httpx.Response(
                200,
                json={"queue": {"slots": [{"nzo_id": "SABnzbd_nzo_abc", "status": "Downloading", "filename": "Saga"}]}},
            )
        if params.get("mode") == "history":
            return httpx.Response(200, json={"history": {"slots": []}})
        return httpx.Response(500, json={"error": "unexpected"})

    client = SABClient("http://downloader.sl", "sab-key", transport=httpx.MockTransport(handler))
    nzo = client.addurl("https://example.test/nzb")
    assert nzo == "SABnzbd_nzo_abc"
    snap = client.job_status(nzo)
    assert snap["status"] == "downloading"
    assert snap["where"] == "queue"


def test_history_completed_storage():
    def handler(request: httpx.Request) -> httpx.Response:
        params = dict(request.url.params)
        if params.get("mode") == "queue":
            return httpx.Response(200, json={"queue": {"slots": []}})
        return httpx.Response(
            200,
            json={
                "history": {
                    "slots": [
                        {
                            "nzo_id": "SABnzbd_nzo_done",
                            "status": "Completed",
                            "storage": "/data/complete/Saga",
                            "name": "Saga",
                        }
                    ]
                }
            },
        )

    client = SABClient("http://downloader.sl", "sab-key", transport=httpx.MockTransport(handler))
    snap = client.job_status("SABnzbd_nzo_done")
    assert snap["status"] == "completed"
    assert snap["storage"] == "/data/complete/Saga"


def test_missing_key_refuses():
    client = SABClient("http://downloader.sl", "")
    try:
        client.addurl("https://example.test/nzb")
        raise AssertionError("expected SABError")
    except SABError as error:
        assert "API key" in str(error)
