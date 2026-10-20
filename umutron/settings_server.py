"""Settings page for the local Docker FastAPI server and provider credentials."""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor

from gi.repository import Adw, Gdk, GLib, Gtk

from .server_manager import (
    ServerEnvironment,
    ServerError,
    ServerManager,
    ServerStatus,
)


class ServerPage(Adw.PreferencesPage):
    def __init__(self, manager: ServerManager, window=None):
        super().__init__(title='Server', icon_name='network-server-symbolic')
        self.manager = manager
        self.window = window
        self._status_pending = False
        self._busy = False
        self._timer = 0
        self._pool = ThreadPoolExecutor(max_workers=1, thread_name_prefix='umutron-server-settings')
        self._generated_key = ''
        self._status_group = Adw.PreferencesGroup(
            title='Local server',
            description='UmuTron uses its own FastAPI server on this computer. '
                        'The desktop only consumes this loopback endpoint.',
        )
        self.add(self._status_group)

        self.status_row = Adw.ActionRow(title='Checking server status…')
        self.status_icon = Gtk.Image.new_from_icon_name('content-loading-symbolic')
        self.status_icon.set_pixel_size(18)
        self.status_row.add_prefix(self.status_icon)
        self.status_group_row = self.status_row
        self._status_group.add(self.status_row)

        self.endpoint_row = Adw.ActionRow(title='Endpoint', subtitle=manager.api_url)
        self._status_group.add(self.endpoint_row)
        self.docker_row = Adw.ActionRow(title='Docker', subtitle='Checking…')
        self._status_group.add(self.docker_row)
        self.repo_row = Adw.ActionRow(title='Server checkout', subtitle='Checking…')
        self._status_group.add(self.repo_row)

        self.progress_row = Adw.ActionRow(title='')
        self.progress_spinner = Gtk.Spinner(valign=Gtk.Align.CENTER)
        self.progress_row.add_prefix(self.progress_spinner)
        self.progress_row.set_visible(False)
        self._status_group.add(self.progress_row)

        controls = Adw.PreferencesGroup(
            title='Server controls',
            description='Install clones the private FastAPI repository when needed, '
                        'writes its environment file, then builds and starts it with Docker Compose.',
        )
        self.add(controls)
        control_row = Adw.ActionRow(title='Docker Compose stack')
        button_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6,
                             valign=Gtk.Align.CENTER)
        self.install_button = Gtk.Button(label='Install & Start')
        self.install_button.add_css_class('suggested-action')
        self.start_button = Gtk.Button(label='Start')
        self.stop_button = Gtk.Button(label='Stop')
        self.refresh_button = Gtk.Button(label='Refresh')
        self.install_button.connect('clicked', lambda *_: self._install())
        self.start_button.connect('clicked', lambda *_: self._start())
        self.stop_button.connect('clicked', lambda *_: self._stop())
        self.refresh_button.connect('clicked', lambda *_: self._refresh_status())
        for control in (self.install_button, self.start_button, self.stop_button, self.refresh_button):
            control.set_valign(Gtk.Align.CENTER)
            button_box.append(control)
        control_row.add_suffix(button_box)
        controls.add(control_row)

        credentials = Adw.PreferencesGroup(
            title='Server environment',
            description='These values are written to the server checkout’s .env file with owner-only '
                        'permissions and passed to the local Docker container. They never go to a '
                        'remote catalog or into catalog.json.',
        )
        self.add(credentials)
        self.key_row = Adw.ActionRow(
            title='Internal API key',
            subtitle='Read-only · generated automatically when the server is installed',
        )
        self.key_entry = Gtk.PasswordEntry(show_peek_icon=True)
        self.key_entry.set_editable(False)
        self.key_entry.set_width_chars(34)
        self.key_entry.set_valign(Gtk.Align.CENTER)
        self.key_row.add_suffix(self.key_entry)
        self.copy_key_button = Gtk.Button(icon_name='edit-copy-symbolic', valign=Gtk.Align.CENTER)
        self.copy_key_button.set_tooltip_text('Copy internal API key')
        self.copy_key_button.connect('clicked', lambda *_: self._copy_key())
        self.key_row.add_suffix(self.copy_key_button)
        credentials.add(self.key_row)

        self.twitch_id_row = Adw.EntryRow(title='Twitch Client ID')
        self.twitch_id_row.set_tooltip_text('Twitch application Client ID used by IGDB')
        credentials.add(self.twitch_id_row)
        self.twitch_secret_row = Adw.PasswordEntryRow(title='Twitch Client Secret')
        self.twitch_secret_row.set_tooltip_text('Twitch application Client Secret used by IGDB')
        credentials.add(self.twitch_secret_row)
        self.live_row = Adw.ActionRow(
            title='Use live IGDB catalog',
            subtitle='IGDB uses Twitch client-credentials OAuth. Turning this on sets '
                     'CATALOG_MODE=igdb and ENABLE_LIVE_IGDB=1 for the local server.',
        )
        self.live_switch = Gtk.Switch(valign=Gtk.Align.CENTER)
        self.live_row.add_suffix(self.live_switch)
        self.live_row.set_activatable_widget(self.live_switch)
        credentials.add(self.live_row)

        apply_row = Adw.ActionRow(
            title='Apply environment',
            subtitle='Saves the key and provider settings. If the server is running, it is recreated '
                     'so the new environment takes effect.',
        )
        self.apply_button = Gtk.Button(label='Save & Apply', valign=Gtk.Align.CENTER)
        self.apply_button.connect('clicked', lambda *_: self._apply())
        apply_row.add_suffix(self.apply_button)
        credentials.add(apply_row)

        self._load_environment()
        self.connect('map', self._start_polling)
        self.connect('unmap', self._stop_polling)
        self.connect('unrealize', self._shutdown)
        self._refresh_status()

    # ------------------------------------------------------------------ state
    def _load_environment(self) -> None:
        repo = self.manager.find_repo()
        values = self.manager.read_environment(repo) if repo else ServerEnvironment()
        self._generated_key = values.internal_api_key or self.manager.generate_key()
        self.key_entry.set_text(self._generated_key)
        self.twitch_id_row.set_text(values.twitch_client_id)
        self.twitch_secret_row.set_text(values.twitch_client_secret)
        self.live_switch.set_active(values.live_catalog)

    def _settings(self) -> ServerEnvironment:
        return ServerEnvironment(
            internal_api_key=self.key_entry.get_text().strip() or self.manager.generate_key(),
            twitch_client_id=self.twitch_id_row.get_text().strip(),
            twitch_client_secret=self.twitch_secret_row.get_text().strip(),
            live_catalog=self.live_switch.get_active(),
        )

    def _set_key(self, value: str) -> None:
        self._generated_key = value
        self.key_entry.set_text(value)

    def _copy_key(self) -> None:
        value = self.key_entry.get_text().strip()
        if not value:
            return
        clipboard = Gdk.Display.get_default().get_clipboard()
        clipboard.set(value)
        if self.window:
            self.window.notify('Internal API key copied.')

    def _set_busy(self, busy: bool, message: str = '') -> None:
        self._busy = busy
        for control in (self.install_button, self.start_button, self.stop_button,
                        self.apply_button, self.refresh_button):
            control.set_sensitive(not busy)
        self.progress_row.set_visible(busy)
        if busy:
            self.progress_row.set_title(message or 'Working…')
            self.progress_spinner.start()
        else:
            self.progress_spinner.stop()
            self.progress_row.set_title('')

    def _progress(self, message: str) -> None:
        GLib.idle_add(self._apply_progress, message)

    def _apply_progress(self, message: str) -> bool:
        if self.get_root() is None:
            return False
        self.progress_row.set_title(message)
        return False

    def _show_error(self, error: BaseException) -> None:
        if self.get_root() is None or not self.window:
            return
        text = str(error)[:4000]
        from .dialogs import message_dialog
        dialog = message_dialog(self.window, 'Server operation failed', text)
        dialog.present()

    # ----------------------------------------------------------------- status
    def _start_polling(self, *_):
        if self._timer:
            return
        self._timer = GLib.timeout_add_seconds(5, self._poll)
        self._refresh_status()

    def _stop_polling(self, *_):
        if self._timer:
            GLib.source_remove(self._timer)
            self._timer = 0

    def _shutdown(self, *_):
        self._stop_polling()
        self._pool.shutdown(wait=False, cancel_futures=True)

    def _poll(self) -> bool:
        self._refresh_status()
        return True

    def _refresh_status(self) -> None:
        if self._status_pending or self._busy:
            return
        self._status_pending = True

        def work() -> ServerStatus:
            return self.manager.status()

        try:
            future = self._pool.submit(work)
        except RuntimeError:
            self._status_pending = False
            return
        future.add_done_callback(lambda done: GLib.idle_add(self._status_loaded, done))

    def _status_loaded(self, future) -> bool:
        self._status_pending = False
        if self.get_root() is None:
            return False
        try:
            status = future.result()
        except Exception:
            self.status_row.set_title('Server status unavailable')
            self.status_row.set_subtitle('Check Docker and the server checkout, then refresh.')
            self.status_icon.set_from_icon_name('dialog-warning-symbolic')
            return False
        self._render_status(status)
        return False

    def _render_status(self, status: ServerStatus) -> None:
        self.status_row.set_title('Running' if status.healthy else 'Not running')
        self.status_row.set_subtitle(
            f'{status.api_url} · healthy' if status.healthy
            else f'{status.api_url} · start it with Docker'
        )
        self.status_icon.set_from_icon_name(
            'emblem-ok-symbolic' if status.healthy else 'dialog-warning-symbolic'
        )
        self.docker_row.set_subtitle(
            'Docker Compose available' if status.docker_available
            else 'Docker or Docker Compose is not available'
        )
        self.repo_row.set_subtitle(
            str(status.repo_dir) if status.repo_installed
            else f'Not installed · will clone to {self.manager.clone_dir}'
        )
        self.install_button.set_label('Install & Start' if not status.repo_installed else 'Rebuild & Start')
        self.start_button.set_sensitive(not self._busy and status.repo_installed)
        self.stop_button.set_sensitive(not self._busy and status.repo_installed and status.healthy)
        self.apply_button.set_sensitive(not self._busy and status.repo_installed)

    # -------------------------------------------------------------- operations
    def _install(self) -> None:
        if self._busy:
            return
        settings = self._settings()
        self._set_busy(True, 'Preparing the local server…')
        self._run(
            lambda: self.manager.install_and_start(settings, progress=self._progress),
            'Local server installed and running.',
        )

    def _start(self) -> None:
        if self._busy:
            return
        repo = self.manager.find_repo()
        if repo is None:
            self._install()
            return
        self._set_busy(True, 'Starting the local server…')
        self._run(
            lambda: (self.manager.start(repo, build=False, progress=self._progress),
                     self.manager.wait_healthy(progress=self._progress),
                     self.manager.activate_local()),
            'Local server is running.',
        )

    def _stop(self) -> None:
        if self._busy:
            return
        repo = self.manager.find_repo()
        if repo is None:
            return
        self._set_busy(True, 'Stopping the local server…')
        self._run(
            lambda: self.manager.stop(repo, progress=self._progress),
            'Local server stopped.',
        )

    def _apply(self) -> None:
        if self._busy:
            return
        repo = self.manager.find_repo()
        if repo is None:
            self._show_error(ServerError('Install the local server before applying environment settings.'))
            return
        settings = self._settings()
        self._set_busy(True, 'Saving server environment…')
        self._run(
            lambda: self.manager.apply_environment(repo, settings, progress=self._progress),
            'Server environment saved and applied.',
        )

    def _run(self, work, success_message: str) -> None:
        try:
            future = self._pool.submit(work)
        except RuntimeError:
            self._set_busy(False)
            return
        future.add_done_callback(
            lambda done: GLib.idle_add(self._operation_done, done, success_message)
        )

    def _operation_done(self, future, success_message: str) -> bool:
        self._set_busy(False)
        if self.get_root() is None:
            return False
        try:
            value = future.result()
        except Exception as error:
            self._show_error(error)
            self._refresh_status()
            return False
        if isinstance(value, ServerEnvironment):
            self._set_key(value.internal_api_key)
        self._load_environment()
        if self.window:
            self.window.notify(success_message)
            try:
                self.window.reconnect_catalog()
            except Exception:
                pass
        self._refresh_status()
        return False
