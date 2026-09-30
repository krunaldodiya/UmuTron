"""Game identity independent of metadata providers and Steam shortcuts."""
from dataclasses import dataclass, field
from uuid import uuid4


@dataclass
class Game:
    title: str
    executable: str
    id: str = field(default_factory=lambda: str(uuid4()))
    metadata_app_id: int | None = None
    shortcut_id: int | None = None

    def set_metadata_source(self, app_id: int) -> None:
        if type(app_id) is not int or app_id <= 0:
            raise ValueError('Steam metadata ID must be a positive integer.')
        self.metadata_app_id = app_id

    def relink(self, executable: str) -> None:
        if not isinstance(executable, str) or not executable.strip():
            raise ValueError('Choose an executable location.')
        self.executable = executable
