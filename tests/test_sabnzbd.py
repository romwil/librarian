import httpx

from librarian.sabnzbd import SABClient, SABError, map_sab_status


def test_map_sab_status_values():
    assert map_sab_status("Downloading") == "downloading"
    assert map_sab_status("Extracting") == "extracting"
    assert map_sab_status("Completed", history=True) == "completed"
    assert map_sab_status("Failed", history=True) == "failed"
    assert map_sab_status("Queued") == "queued"
    assert map_sab_status("Propagating") == "queued"
    assert map_sab_status("Grabbing") == "queued"
    assert map_sab_status("Verifying") == "extracting"


def test_addurl_and_job_status_nzo_id():
    def handler(request: httpx.Request) -> httpx.Response:
        params = dict(request.url.params)
        if params.get("mode") == "addurl":
            return httpx.Response(200, json={"status": True, "nzo_ids": ["SABnzbd_nzo_abc"]})
        if params.get("mode") == "queue":
            return httpx.Response(
                200,
                json={
                    "queue": {
                        "slots": [
                            {
                                "nzo_id": "SABnzbd_nzo_abc",
                                "status": "Downloading",
                                "filename": "Saga",
                                "percentage": "42",
                                "mb": "10",
                                "mbleft": "6",
                            }
                        ]
                    }
                },
            )
        if params.get("mode") == "get_files":
            return httpx.Response(
                200,
                json={"files": [{"filename": "saga.par2", "status": "finished"}]},
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
    assert snap["percentage"] == "42"
    assert snap["name"] == "Saga"


def test_addfile_posts_multipart_nzb():
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["method"] = request.method
        seen["content_type"] = request.headers.get("content-type", "")
        body = request.content or b""
        seen["has_nzb"] = b"<nzb" in body
        seen["has_mode"] = b"name=\"mode\"" in body or b"mode" in body
        return httpx.Response(200, json={"status": True, "nzo_ids": ["SABnzbd_nzo_file"]})

    client = SABClient("http://downloader.sl", "sab-key", transport=httpx.MockTransport(handler))
    nzo = client.addfile(b'<?xml version="1.0"?><nzb></nzb>', filename="saga.nzb", nzbname="Saga", cat="books")
    assert nzo == "SABnzbd_nzo_file"
    assert seen["method"] == "POST"
    assert "multipart" in seen["content_type"]
    assert seen["has_nzb"] is True


def test_grabbing_wait_label_surfaces_in_sab_status():
    def handler(request: httpx.Request) -> httpx.Response:
        params = dict(request.url.params)
        if params.get("mode") == "queue":
            return httpx.Response(
                200,
                json={
                    "queue": {
                        "slots": [
                            {
                                "nzo_id": "SABnzbd_nzo_wait",
                                "status": "Grabbing",
                                "filename": "Wait.Title",
                                "labels": ["WAIT 89 sec"],
                                "percentage": "0",
                                "mb": "0",
                                "mbleft": "0",
                            }
                        ]
                    }
                },
            )
        if params.get("mode") == "get_files":
            return httpx.Response(200, json={"files": []})
        return httpx.Response(200, json={"history": {"slots": []}})

    client = SABClient("http://downloader.sl", "sab-key", transport=httpx.MockTransport(handler))
    snap = client.job_status("SABnzbd_nzo_wait")
    assert snap["status"] == "queued"
    assert snap["sab_status"] == "Grabbing · WAIT 89 sec"


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
    assert snap["fail_message"] == ""


def test_history_failed_exposes_fail_message():
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
                            "nzo_id": "SABnzbd_nzo_bad",
                            "status": "Failed",
                            "fail_message": "Unpacking failed, archive is damaged",
                            "name": "VA-Dump.Name-202",
                            "storage": "/downloads/incomplete/VA-Dump.Name-202",
                        }
                    ]
                }
            },
        )

    client = SABClient("http://downloader.sl", "sab-key", transport=httpx.MockTransport(handler))
    snap = client.job_status("SABnzbd_nzo_bad")
    assert snap["status"] == "failed"
    assert snap["fail_message"] == "Unpacking failed, archive is damaged"
    assert snap["name"] == "VA-Dump.Name-202"
    assert snap["where"] == "history"


def test_get_files_uses_documented_value_param():
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        params = dict(request.url.params)
        seen["mode"] = params.get("mode")
        seen["value"] = params.get("value")
        return httpx.Response(200, json={"files": [{"filename": "book.rar", "status": "finished"}]})

    client = SABClient("http://downloader.sl", "sab-key", transport=httpx.MockTransport(handler))
    files = client.get_files("SABnzbd_nzo_abc")
    assert seen == {"mode": "get_files", "value": "SABnzbd_nzo_abc"}
    assert files[0]["filename"] == "book.rar"


def test_missing_key_refuses():
    client = SABClient("http://downloader.sl", "")
    try:
        client.addurl("https://example.test/nzb")
        raise AssertionError("expected SABError")
    except SABError as error:
        assert "API key" in str(error)
