"""Generated, comment-only Cura quality-profile provenance capture."""

PROFILE_METADATA_CODE = r'''
class _FilamentManagerProfileRecorder:
    """Bind the displayed quality name to a newly sliced plate, never export-time state."""

    def __init__(self, application, backend):
        self.application = application
        self.backend = backend
        self.name = None
        backend.slicingStarted.connect(self.started)
        backend.backendStateChange.connect(self.finished)
        if hasattr(backend, "slicingCancelled"):
            backend.slicingCancelled.connect(self.cancelled)

    def cancelled(self, *args):
        self.name = None

    def started(self, *args):
        try:
            # Cura assigns its plate ID after emitting slicingStarted. Capture
            # the selected quality now and bind the finished engine run later.
            self.name = None
            stack = self.application.getGlobalContainerStack()
            if stack is None:
                return
            quality = stack.qualityChanges
            if quality.getId() == "empty_quality_changes":
                quality = stack.quality
            name = quality.getName()
            if isinstance(name, str) and name.strip() and len(name) <= 255:
                self.name = " ".join(name.split())
        except Exception:
            Logger.log("w", "Filament Manager could not capture the sliced quality profile")

    def finished(self, state):
        try:
            from UM.Backend.Backend import BackendState
            if state != BackendState.Done:
                return
            plate = getattr(self.backend, "_start_slice_job_build_plate", None)
            name, self.name = self.name, None
            if name is None or type(plate) is not int:
                return
            scene = self.application.getController().getScene()
            data = getattr(scene, "gcode_dict", {}).get(plate)
            if not isinstance(data, list) or not data or not isinstance(data[0], str):
                return
            # One inert ASCII JSON comment; preserve toolpath, thumbnails and
            # all post-processing blocks byte-for-byte. Imported files are not touched.
            data.insert(0, ";FM_CURA_PROFILE_JSON:" + json.dumps(name, ensure_ascii=True) + "\n")
        except Exception:
            Logger.log("w", "Filament Manager could not retain sliced profile metadata")


def _install_profile_recorder(application):
    """Install only on backends exposing the verified Cura slicing lifecycle."""
    try:
        getter = getattr(application, "getBackend", None)
        backend = getter() if getter is not None else None
        signals = ("slicingStarted", "backendStateChange")
        if backend is None or not all(hasattr(backend, key) for key in signals):
            return None
        return _FilamentManagerProfileRecorder(application, backend)
    except Exception:
        Logger.log("w", "Filament Manager profile metadata is unavailable on this backend")
        return None
'''
