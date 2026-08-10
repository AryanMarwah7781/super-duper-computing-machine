import json
from pathlib import Path

import pytest

from assist_desktop import lessons

CATALOG = Path(__file__).resolve().parent.parent / "data" / "lessons.json"


def sent(signal: str, value: str) -> str:
    return ('2026-08-07 12:00:15,432 [12] DEBUG - MsgQueueDataHandler.'
            'SendVIOData(): ActiveMQ data to send to EC2. Data: '
            f'{{"signal":"{signal}","value":"{value}"}}. Queue: /queue/COMMANDARM')


def recv(*pairs: tuple[str, str]) -> str:
    body = ",".join(f'{{"signal":"{s}","value":"{v}"}}' for s, v in pairs)
    return ('2026-08-07 12:00:15,680 [17] DEBUG - MsgQueueDataHandler.'
            'OnStompMessageReceived(): ActiveMQ data received from EC2: '
            f'{{"signals":[{body}]}}')


def watcher(*rules: dict) -> lessons.StepWatcher:
    return lessons.StepWatcher(
        [lessons.Trigger.from_dict(i, r) for i, r in enumerate(rules, start=1)])


# -- the shipped catalog ---------------------------------------------------

def test_catalog_loads_and_every_step_has_copy():
    catalog = lessons.load_catalog(CATALOG)
    lesson_ids = [lesson["id"]
                  for category in catalog["categories"]
                  for lesson in category["lessons"]]
    assert "spray" in lesson_ids
    for category in catalog["categories"]:
        for lesson in category["lessons"]:
            assert lesson["steps"], f"{lesson['id']} has no steps"
            for step in lesson["steps"]:
                assert step["header"] and step["body"]


def test_a_missing_catalog_is_empty_rather_than_fatal(tmp_path):
    assert lessons.load_catalog(tmp_path / "nope.json")["categories"] == []


def test_console_icons_referenced_by_the_catalog_exist():
    catalog = lessons.load_catalog(CATALOG)
    public = CATALOG.parent.parent / "ui" / "public"
    for category in catalog["categories"]:
        for lesson in category["lessons"]:
            for step in lesson["steps"]:
                image = (step.get("icon") or {}).get("image")
                if image:
                    assert (public / image).is_file(), image


# -- matching --------------------------------------------------------------

def test_a_press_completes_its_step():
    w = watcher({"signals": ["PLT_AIC_SolutionPump"], "condition": "equals",
                 "value": "1"})
    assert w.feed_line(sent("PLT_AIC_SolutionPump", "1")) == [1]


def test_a_step_completes_once_only():
    w = watcher({"signals": ["PLT_AIC_SolutionPump"], "condition": "equals",
                 "value": "1"})
    w.feed_line(sent("PLT_AIC_SolutionPump", "1"))
    assert w.feed_line(sent("PLT_AIC_SolutionPump", "1")) == []


def test_every_signal_on_a_received_line_is_read():
    # A received line carries an array. Reading only the first pair drops the
    # rest and makes indicator-driven steps look broken.
    w = lessons.StepWatcher([
        lessons.Trigger(1, ("PLT_AIC_Rate2ControlIndicator",), "equals", "1",
                        source="recv"),
    ])
    line = recv(("PLT_AIC_Rate1ControlIndicator", "0"),
                ("PLT_AIC_Rate2ControlIndicator", "1"))
    assert w.feed_line(line) == [1]


def test_cache_chatter_is_not_an_event():
    w = watcher({"signals": ["PLT_AIC_ParkBrake"], "condition": "equals",
                 "value": "1"})
    noisy = ('2026-08-07 12:00:15,432 DEBUG - SBMRequestHandler.'
             'HasVioValueChanged(): SendVIOData(). Data: '
             '{"signal":"PLT_AIC_ParkBrake","value":"1"}')
    assert w.feed_line(noisy) == []


def test_a_received_value_does_not_complete_a_step_that_wants_a_press():
    w = watcher({"signals": ["PLT_AIC_SolutionPump"], "condition": "equals",
                 "value": "1"})
    assert w.feed_line(recv(("PLT_AIC_SolutionPump", "1"))) == []


def test_an_ordered_step_waits_for_the_one_before_it():
    w = watcher(
        {"signals": ["PLT_AIC_Rate1Control"], "condition": "equals", "value": "1"},
        {"signals": ["PLT_AIC_Rate2Control"], "condition": "equals",
         "value": "1", "requires_step": 1},
    )
    assert w.feed_line(sent("PLT_AIC_Rate2Control", "1")) == []
    assert w.feed_line(sent("PLT_AIC_Rate1Control", "1")) == [1]
    assert w.feed_line(sent("PLT_AIC_Rate2Control", "1")) == [2]


def test_a_resumed_step_unblocks_the_one_that_waits_on_it():
    w = watcher(
        {"signals": ["PLT_AIC_Rate1Control"], "condition": "equals", "value": "1"},
        {"signals": ["PLT_AIC_Rate2Control"], "condition": "equals",
         "value": "1", "requires_step": 1},
    )
    w.done.add(1)  # done in an earlier session
    assert w.feed_line(sent("PLT_AIC_Rate2Control", "1")) == [2]


def test_a_malformed_analog_literal_is_not_a_press():
    # VIO_GPS_Speed carries values like "0.3.2E05" in the reference logs.
    w = watcher({"signals": ["VIO_GPS_Speed"], "condition": "nonzero"})
    assert w.feed_line(sent("VIO_GPS_Speed", "0.3.2E05")) == []


# -- the pedal, which arms a button that means two things ------------------

def pedal(pressed: bool) -> str:
    return ('2026-08-07 12:00:15,432 [33] DEBUG - HID: '
            f'ReversePedal(GenericDesktopY) pressed={pressed}')


def fold_watcher() -> lessons.StepWatcher:
    """Frame height and fold, in the order the lesson teaches them. Both are
    the same button and the same signal; only the pedal separates them."""
    return watcher(
        {"signals": ["PLT_MHC_CenterBoomRaise"], "condition": "equals",
         "value": "1"},
        {"signals": ["PLT_MHC_CenterBoomRaise"], "condition": "equals",
         "value": "1", "requires_step": 1,
         "armed_by": {"signal": "HID_ReversePedal", "value": "1"}},
    )


def test_the_pedal_is_read_from_its_raw_hid_line():
    # It never becomes a signal. Unread, a fold step can never be armed.
    w = watcher({"signals": ["HID_ReversePedal"], "condition": "equals",
                 "value": "1", "source": "hid"})
    assert w.feed_line(pedal(True)) == [1]


def test_the_same_button_folds_only_after_the_pedal():
    w = fold_watcher()
    assert w.feed_line(sent("PLT_MHC_CenterBoomRaise", "1")) == [1]
    # No pedal: this is frame height again, not the fold.
    assert w.feed_line(sent("PLT_MHC_CenterBoomRaise", "1")) == []
    w.feed_line(pedal(True))
    assert w.feed_line(sent("PLT_MHC_CenterBoomRaise", "1")) == [2]


def test_the_pedal_arms_one_press_only():
    w = fold_watcher()
    w.feed_line(sent("PLT_MHC_CenterBoomRaise", "1"))   # step 1, frame height
    w.feed_line(pedal(True))
    assert w.feed_line(sent("PLT_MHC_CenterBoomRaise", "1")) == [2]
    assert w._armed == set()


def test_letting_the_pedal_go_does_not_disarm_it():
    # The pedal is worked and released before the hand reaches the button.
    w = fold_watcher()
    w.feed_line(sent("PLT_MHC_CenterBoomRaise", "1"))
    w.feed_line(pedal(True))
    w.feed_line(pedal(False))
    assert w.feed_line(sent("PLT_MHC_CenterBoomRaise", "1")) == [2]


# -- the handle, which has no fixed neutral --------------------------------

def handle_watcher() -> lessons.StepWatcher:
    return watcher(
        {"signals": ["PLT_HydroHandlePosition"], "condition": "off_baseline",
         "value": "12"},
        {"signals": ["PLT_HydroHandlePosition"], "condition": "back_to_baseline",
         "value": "12", "requires_step": 1},
    )


def rest_at(w: lessons.StepWatcher, value: int) -> list[int]:
    done = []
    for _ in range(lessons.BASELINE_SAMPLES):
        done += w.feed_line(sent("PLT_HydroHandlePosition", str(value)))
    return done


def test_neutral_is_measured_not_assumed():
    for resting in (174, 238):  # two real sessions, same physical handle
        w = handle_watcher()
        assert rest_at(w, resting) == []
        assert w.feed_line(sent("PLT_HydroHandlePosition",
                                str(resting + 20))) == [1]


def test_returning_to_neutral_needs_the_handle_to_have_left_it():
    w = handle_watcher()
    rest_at(w, 174)
    # Sitting in the band was never leaving it, so there is nothing to return
    # from — the trainer must not tick both steps off a handle nobody touched.
    assert w.feed_line(sent("PLT_HydroHandlePosition", "176")) == []
    assert w.feed_line(sent("PLT_HydroHandlePosition", "210")) == [1]
    assert w.feed_line(sent("PLT_HydroHandlePosition", "176")) == [2]


# -- tailing ---------------------------------------------------------------

def test_the_tailer_reads_only_what_is_appended_after_it_opens(tmp_path):
    log = tmp_path / "log.txt"
    log.write_text(sent("PLT_AIC_SolutionPump", "1") + "\n", encoding="utf-8")

    seen: list[int] = []
    tailer = lessons.LogTailer(
        str(log),
        watcher({"signals": ["PLT_AIC_SolutionPump"], "condition": "equals",
                 "value": "1"}),
        on_step=seen.append)

    # Yesterday's press is already in the file. Replaying it would complete
    # the lesson before the operator touched anything.
    assert tailer.poll() == []
    with log.open("a", encoding="utf-8") as f:
        f.write(sent("PLT_AIC_SolutionPump", "1") + "\n")
    assert tailer.poll() == [1]
    assert seen == [1]


def test_a_truncated_log_is_read_from_the_start(tmp_path):
    log = tmp_path / "log.txt"
    log.write_text("x" * 500, encoding="utf-8")
    tailer = lessons.LogTailer(
        str(log),
        watcher({"signals": ["PLT_AIC_ParkBrake"], "condition": "equals",
                 "value": "1"}),
        on_step=lambda i: None)
    log.write_text(sent("PLT_AIC_ParkBrake", "1") + "\n", encoding="utf-8")
    assert tailer.poll() == [1]


def test_a_log_that_is_not_there_yet_does_not_raise(tmp_path):
    tailer = lessons.LogTailer(str(tmp_path / "absent.txt"), watcher(),
                               on_step=lambda i: None)
    assert tailer.poll() == []


def test_the_environment_overrides_the_catalog_log_path(monkeypatch):
    catalog = {"log_path": "C:/simulator/log.txt"}
    assert lessons.sim_log_path(catalog) == "C:/simulator/log.txt"
    monkeypatch.setenv("ASSIST_SIM_LOG", "D:/elsewhere/log.txt")
    assert lessons.sim_log_path(catalog) == "D:/elsewhere/log.txt"


# -- progress --------------------------------------------------------------

@pytest.fixture
def progress(tmp_path):
    return lessons.ProgressStore(tmp_path / "lesson_progress.json")


def test_progress_survives_a_restart(progress, tmp_path):
    progress.complete("ari", "spray", 2)
    progress.complete("ari", "spray", 1)
    reopened = lessons.ProgressStore(tmp_path / "lesson_progress.json")
    assert reopened.steps_done("ari", "spray") == [1, 2]


def test_progress_is_per_operator(progress):
    progress.complete("ari", "spray", 1)
    assert progress.steps_done("marcus", "spray") == []


def test_a_step_is_recorded_once(progress):
    progress.complete("ari", "spray", 1)
    progress.complete("ari", "spray", 1)
    assert progress.steps_done("ari", "spray") == [1]


def test_reset_clears_the_steps_but_keeps_the_visit(progress):
    progress.opened("ari", "spray")
    progress.complete("ari", "spray", 1)
    progress.reset("ari", "spray")
    assert progress.steps_done("ari", "spray") == []
    assert progress.summary("ari")["spray"]["last_opened"]


def test_a_signed_out_screen_records_nothing(progress, tmp_path):
    progress.complete("", "spray", 1)
    assert not (tmp_path / "lesson_progress.json").exists()


def test_a_corrupt_progress_file_does_not_stop_the_app(tmp_path):
    path = tmp_path / "lesson_progress.json"
    path.write_text("{ not json", encoding="utf-8")
    assert lessons.ProgressStore(path).summary("ari") == {}


def test_progress_stays_readable_on_disk(progress, tmp_path):
    progress.complete("ari", "spray", 1)
    raw = json.loads((tmp_path / "lesson_progress.json").read_text(encoding="utf-8"))
    assert raw["operators"]["ari"]["spray"]["steps_done"] == [1]
