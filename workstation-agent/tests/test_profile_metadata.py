"""Exercise generated slice-time comments without touching Cura files or motion."""

import json
import sys
from types import ModuleType, SimpleNamespace

from filament_manager_agent.cura_profile_metadata import PROFILE_METADATA_CODE


def test_profile_capture_is_slice_bound_and_preserves_gcode(monkeypatch):
    """Changing profiles after slicing cannot relabel saved data; cancellation clears evidence."""
    module = ModuleType("UM.Backend.Backend")
    module.BackendState = SimpleNamespace(Done=2)
    monkeypatch.setitem(sys.modules, "UM.Backend.Backend", module)
    signal = SimpleNamespace(connect=lambda callback: None)
    backend = SimpleNamespace(slicingStarted=signal, slicingCancelled=signal, backendStateChange=signal)
    quality = SimpleNamespace(getName=lambda: 'Fine "Silk"', getId=lambda: "custom")
    scene = SimpleNamespace(gcode_dict={1: [";thumbnail begin\nABC\n", "G1 X2\n"]})
    app = SimpleNamespace(
        getGlobalContainerStack=lambda: SimpleNamespace(qualityChanges=quality, quality=quality),
        getController=lambda: SimpleNamespace(getScene=lambda: scene),
        getBackend=lambda: backend,
    )
    namespace = {"json": json, "Logger": SimpleNamespace(log=lambda *args: None)}
    exec(compile(PROFILE_METADATA_CODE, "generated-profile-metadata", "exec"), namespace)  # noqa: S102
    recorder = namespace["_install_profile_recorder"](app)
    recorder.started()  # Cura has not assigned a plate yet.
    backend._start_slice_job_build_plate = 1
    quality.getName = lambda: "Changed after slicing"
    recorder.finished(2)
    assert scene.gcode_dict[1] == [
        ';FM_CURA_PROFILE_JSON:"Fine \\"Silk\\""\n',
        ";thumbnail begin\nABC\n",
        "G1 X2\n",
    ]
    recorder.finished(2)
    assert len(scene.gcode_dict[1]) == 3
    recorder.started()
    recorder.cancelled()
    recorder.finished(2)
    assert len(scene.gcode_dict[1]) == 3
    assert namespace["_install_profile_recorder"](SimpleNamespace()) is None
    # A built-in quality uses the stock name, not the empty changes container.
    app.getGlobalContainerStack = lambda: SimpleNamespace(
        qualityChanges=SimpleNamespace(getId=lambda: "empty_quality_changes"),
        quality=SimpleNamespace(getName=lambda: "Standard Quality"),
    )
    scene.gcode_dict[1] = ["G1 X3\n"]
    recorder.started()
    recorder.finished(2)
    assert scene.gcode_dict[1] == [
        ';FM_CURA_PROFILE_JSON:"Standard Quality"\n',
        "G1 X3\n",
    ]
