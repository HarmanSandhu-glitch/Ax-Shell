import json
import os
import math
import subprocess
from pathlib import Path
from datetime import datetime, timedelta
import shutil
import calendar as cal

import gi
from fabric.widgets.box import Box
from fabric.widgets.label import Label
from fabric.widgets.button import Button
from fabric.widgets.entry import Entry
from fabric.widgets.eventbox import EventBox

import modules.icons as icons

gi.require_version('Gtk', '3.0')
from gi.repository import GLib, Gtk


class Tracker(Box):
    """Task tracking and time management module."""
    
    STATE_FILE = Path(os.path.expanduser("~/.tracker_data.json"))
    
    def __init__(self):
        super().__init__(
            name="tracker",
            orientation="h",
            spacing=8,
            h_expand=True,
            v_expand=True,
        )
        
        # State variables
        self.tasks = []
        self.time_logs = []
        self.reminders = []
        self.active_timer = None
        self.timer_source_id = None
        self.is_timer_running = False
        self.next_task_id = 1  # Never reuse task IDs
        self.selected_task_id = None
        self.reminder_source_ids = {}
        self.last_tick_time = None
        self._suppress_combo_handler = False
        self.reminder_tick_id = None
        
        self.load_state()
        self._ensure_active_task_valid()
        self.setup_ui()
        self.refresh_timer_display()
        self.schedule_all_reminders()
        self.start_reminder_tick_loop()
        
        # Restore timer state
        if self.active_timer and self.active_timer.get('start_time'):
            self.is_timer_running = True
            self.start_timer_loop()
            self.update_play_btn_icon()
            self.stop_btn.set_sensitive(True)
            self.timer_combo.set_sensitive(False)
        
        self.show_all()
    
    def setup_ui(self):
        """Create compact UI layout."""
        # Left column: Goals
        left_col = Box(name="tracker-goals-column", orientation="v", spacing=8, h_expand=True, v_expand=True)
        left_col.add(self.create_goals_section())
        self.add(left_col)
        
        # Right column: Reports + Timer/Reminders
        right_col = Box(name="tracker-right-column", orientation="v", spacing=8, h_expand=True, v_expand=True)
        
        # Top row: Weekly + Monthly
        top_row = Box(orientation="h", spacing=8, h_expand=True)
        top_row.add(self.create_weekly_section())
        top_row.add(self.create_monthly_section())
        right_col.add(top_row)
        
        # Bottom row: Timer + Reminders
        bottom_row = Box(orientation="h", spacing=8, h_expand=True)
        bottom_row.add(self.create_timer_section())
        bottom_row.add(self.create_reminders_section())
        right_col.add(bottom_row)
        
        self.add(right_col)
    
    def create_goals_section(self):
        """Create Today's Goals section."""
        section = Box(name="tracker-goals-section", orientation="v", spacing=4, h_expand=True, v_expand=True)
        
        # Header
        header = Label(name="tracker-section-title", label="Today's Goals")
        header.set_xalign(0)
        section.add(header)
        
        # Tasks container
        self.tasks_box = Box(name="tracker-tasks-list", orientation="v", spacing=2, v_expand=True)
        self.refresh_tasks()
        section.add(self.tasks_box)
        
        # Add task row
        add_row = Box(orientation="h", spacing=4)
        self.task_entry = Entry(name="tracker-task-entry", h_expand=True)
        self.task_entry.set_placeholder_text("Task")
        self.task_entry.connect("activate", lambda w: self.add_task())
        
        self.units_entry = Entry(name="tracker-units-entry")
        self.units_entry.set_placeholder_text("1")
        self.units_entry.set_width_chars(4)
        self.units_entry.connect("activate", lambda w: self.add_task())
        
        add_btn = Button(name="tracker-add-btn", child=Label(markup=icons.add))
        add_btn.connect("clicked", lambda w: self.add_task())
        
        add_row.add(self.task_entry)
        add_row.add(self.units_entry)
        add_row.add(add_btn)
        section.add(add_row)
        
        return section
    
    def create_timer_section(self):
        """Create Timer section."""
        section = Box(name="tracker-timer-section", orientation="v", spacing=4, h_expand=True)
        
        header = Label(name="tracker-section-title", label="Timer")
        header.set_xalign(0)
        section.add(header)
        
        # Timer display
        self.timer_display = Label(name="tracker-timer-display", label="0:00")
        section.add(self.timer_display)
        
        # Controls
        controls = Box(orientation="h", spacing=8, h_align="center")
        
        # Play button with label that we'll update
        self.play_btn_label = Label(markup=icons.play)
        self.play_btn = Button(name="tracker-play-btn", child=self.play_btn_label)
        self.play_btn.connect("clicked", self.on_play_clicked)
        
        # Stop button
        self.stop_btn_label = Label(markup=icons.stop)
        self.stop_btn = Button(name="tracker-stop-btn", child=self.stop_btn_label)
        self.stop_btn.connect("clicked", self.on_stop_clicked)
        self.stop_btn.set_sensitive(False)
        
        controls.add(self.play_btn)
        controls.add(self.stop_btn)
        section.add(controls)
        
        # Task selector
        self.timer_combo = Gtk.ComboBoxText()
        self.timer_combo.set_name("tracker-task-combo")
        self.update_timer_combo()
        self.timer_combo.connect("changed", self.on_timer_task_changed)
        section.add(self.timer_combo)
        
        return section
    
    def update_play_btn_icon(self):
        """Update play button icon based on timer state."""
        if self.is_timer_running:
            self.play_btn_label.set_markup(icons.pause)
        else:
            self.play_btn_label.set_markup(icons.play)
    
    def create_reminders_section(self):
        """Create Reminders section."""
        section = Box(name="tracker-reminders-section", orientation="v", spacing=4, h_expand=True)
        
        header = Label(name="tracker-section-title", label="Reminders")
        header.set_xalign(0)
        section.add(header)
        
        # Reminders list
        self.reminders_box = Box(name="tracker-reminders-list", orientation="v", spacing=2, v_expand=True)
        self.refresh_reminders()
        section.add(self.reminders_box)
        
        # Add reminder row
        add_row = Box(orientation="h", spacing=4)
        self.reminder_entry = Entry(name="tracker-reminder-entry", h_expand=True)
        self.reminder_entry.set_placeholder_text("Remind")
        self.reminder_entry.connect("activate", lambda w: self.add_reminder())
        
        self.reminder_time = Entry(name="tracker-time-entry")
        self.reminder_time.set_placeholder_text("Minutes (e.g. 15)")
        self.reminder_time.set_width_chars(10)
        self.reminder_time.connect("activate", lambda w: self.add_reminder())
        
        add_btn = Button(name="tracker-add-btn", child=Label(markup=icons.add))
        add_btn.connect("clicked", lambda w: self.add_reminder())
        
        add_row.add(self.reminder_entry)
        add_row.add(self.reminder_time)
        add_row.add(add_btn)
        section.add(add_row)
        
        return section
    
    def create_weekly_section(self):
        """Create Weekly Report section."""
        section = Box(name="tracker-weekly-report", orientation="v", spacing=4, h_expand=True)
        
        header = Label(name="tracker-section-title", label="Weekly Time Report")
        header.set_xalign(0)
        section.add(header)
        
        # Chart area
        self.chart_area = Gtk.DrawingArea()
        self.chart_area.set_name("tracker-weekly-chart")
        self.chart_area.set_size_request(200, 120)
        self.chart_area.set_vexpand(True)
        self.chart_area.set_hexpand(True)
        self.chart_area.connect("draw", self.draw_spline_chart)
        section.add(self.chart_area)

        # Export controls
        export_row = Box(orientation="h", spacing=4)
        export_json_btn = Button(name="tracker-export-json", child=Label(label="Export JSON"))
        export_json_btn.connect("clicked", lambda w: self.export_time_logs_json())
        export_csv_btn = Button(name="tracker-export-csv", child=Label(label="Export CSV"))
        export_csv_btn.connect("clicked", lambda w: self.export_time_logs_csv())
        export_row.add(export_json_btn)
        export_row.add(export_csv_btn)
        section.add(export_row)
        
        return section
    
    def create_monthly_section(self):
        """Create Monthly Report section."""
        section = Box(name="tracker-monthly-report", orientation="v", spacing=4, h_expand=True)
        section.set_size_request(140, -1)
        section.set_hexpand(False)
        
        header = Label(name="tracker-section-title", label="Monthly Report")
        header.set_xalign(0)
        section.add(header)
        
        # Calendar grid
        self.calendar_grid = Gtk.Grid()
        self.calendar_grid.set_name("tracker-monthly-grid")
        self.calendar_grid.set_row_spacing(2)
        self.calendar_grid.set_column_spacing(2)
        self.calendar_grid.set_row_homogeneous(True)
        self.calendar_grid.set_column_homogeneous(True)
        self.calendar_grid.set_size_request(140, -1)
        self.calendar_grid.set_hexpand(False)
        self.refresh_calendar()
        section.add(self.calendar_grid)
        
        return section
    
    # === Task Functions ===
    def refresh_tasks(self):
        """Refresh tasks display."""
        for c in self.tasks_box.get_children():
            self.tasks_box.remove(c)
        
        for task in self.tasks:
            row = self.make_task_row(task)
            self.tasks_box.add(row)
        self.tasks_box.show_all()
    
    def make_task_row(self, task):
        """Create a task row widget."""
        row = Box(name="tracker-task-row", orientation="h", spacing=4)
        
        # Name + time
        info = Box(orientation="h", spacing=8, h_expand=True)
        name = Label(name="tracker-task-name", label=task['name'])
        name.set_xalign(0)
        info.add(name)
        
        # Calculate today's time
        today = datetime.now().date()
        secs = sum(log['duration'] for log in self.time_logs 
                   if log['task_id'] == task['id'] and 
                   datetime.fromisoformat(log['start']).date() == today)
        time_str = f"{int(secs//3600)}:{int((secs%3600)//60):02d}"
        time_lbl = Label(name="tracker-task-time", label=time_str)
        time_lbl.set_xalign(0)
        time_lbl.h_expand = False
        info.add(time_lbl)
        row.add(info)
        
        tid = task['id']
        # - button (decrease)
        minus_btn = Button(name="tracker-task-btn", child=Label(label="−"))
        minus_btn.connect("clicked", lambda w, t=tid: self.dec_task(t))
        row.add(minus_btn)
        # Progress
        prog = Label(name="tracker-task-progress", label=f"{task['done']:.0f}/{task['units']:.0f}")
        row.add(prog)
        
        
        # + button (increase)
        plus_btn = Button(name="tracker-task-btn", child=Label(markup=icons.add))
        plus_btn.connect("clicked", lambda w, t=tid: self.inc_task(t))
        row.add(plus_btn)
        
        # Delete button
        del_btn = Button(name="tracker-reminder-delete", child=Label(markup=icons.cancel))
        del_btn.connect("clicked", lambda w, t=tid: self.del_task(t))
        row.add(del_btn)
        
        return row
    
    def add_task(self):
        """Add new task."""
        name = self.task_entry.get_text().strip()
        if not name:
            return
        try:
            units = float(self.units_entry.get_text().strip() or "1")
        except ValueError:
            units = 1.0
        
        tid = self.next_task_id
        self.next_task_id += 1
        self.tasks.append({
            'id': tid,
            'name': name,
            'units': units,
            'done': 0.0,
            'created': datetime.now().isoformat(),
            'archived': False,
            'is_today': True
        })
        self.task_entry.set_text("")
        self.units_entry.set_text("")
        self.refresh_tasks()
        self.update_timer_combo()
        self.save_state()
    
    def inc_task(self, tid):
        """Increment task progress."""
        task_name = None
        completed = False
        for t in self.tasks:
            if t['id'] == tid:
                t['done'] = min(t['done'] + 1, t['units'])
                if t['done'] >= t['units']:
                    task_name = t['name']
                    completed = True
                break
        
        # Use GLib.idle_add to schedule UI updates for smoother performance
        def update_ui():
            self.refresh_tasks()
            self.save_state()
            return False  # Don't repeat
        
        GLib.idle_add(update_ui)
        
        # Send notification using subprocess to avoid blocking
        if completed and task_name:
            try:
                subprocess.Popen(
                    ['notify-send', 'Task Complete! 🎉', f'Completed: {task_name}'],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    start_new_session=True
                )
            except Exception:
                pass
    
    def dec_task(self, tid):
        """Decrement task progress."""
        for t in self.tasks:
            if t['id'] == tid:
                t['done'] = max(t['done'] - 1, 0)
                break
        
        def update_ui():
            self.refresh_tasks()
            self.save_state()
            return False
        
        GLib.idle_add(update_ui)
    
    def del_task(self, tid):
        """Delete a task (keeps time logs for historical data)."""
        if self.active_timer and self.active_timer.get('task_id') == tid:
            self.stop_timer()
            self.selected_task_id = None
        self.tasks = [t for t in self.tasks if t['id'] != tid]
        self.refresh_tasks()
        self.refresh_chart()
        self.refresh_calendar()
        self.update_timer_combo()
        self.save_state()
    
    def update_timer_combo(self):
        """Update timer task combo."""
        self._suppress_combo_handler = True
        try:
            self.timer_combo.remove_all()
            for t in self.tasks:
                self.timer_combo.append_text(t['name'])
            # Prefer the running task, otherwise the last selected task
            preferred_id = None
            if self.active_timer:
                preferred_id = self.active_timer.get('task_id')
            elif self.selected_task_id:
                preferred_id = self.selected_task_id
            idx = None
            if preferred_id is not None:
                for i, t in enumerate(self.tasks):
                    if t['id'] == preferred_id:
                        idx = i
                        break
            if idx is None and self.tasks:
                idx = 0
                self.selected_task_id = self.tasks[0]['id']
            if idx is not None:
                self.timer_combo.set_active(idx)
        finally:
            self._suppress_combo_handler = False

    def _ensure_active_task_valid(self):
        """Ensure saved active timer references an existing task; clear otherwise."""
        if self.active_timer:
            tid = self.active_timer.get('task_id')
            if tid is None or not any(t['id'] == tid for t in self.tasks):
                self.active_timer = None
                self.is_timer_running = False
                self.selected_task_id = None
                self.timer_source_id = None
                try:
                    self.send_notification('Tracker', 'Saved timer cleared because its task is missing')
                except Exception:
                    pass

    def on_timer_task_changed(self, widget):
        """Persist the selected task when user changes the dropdown."""
        if self._suppress_combo_handler:
            return
        idx = self.timer_combo.get_active()
        if 0 <= idx < len(self.tasks):
            self.selected_task_id = self.tasks[idx]['id']
            self.save_state()
    
    # === Timer Functions ===
    def on_play_clicked(self, widget):
        """Handle play button click."""
        if self.is_timer_running:
            self.pause_timer()
        else:
            self.start_timer()
    
    def on_stop_clicked(self, widget):
        """Handle stop button click."""
        self.stop_timer()
    
    def start_timer(self):
        """Start timer."""
        idx = self.timer_combo.get_active()
        if idx < 0 or idx >= len(self.tasks):
            return
        
        task = self.tasks[idx]
        self.selected_task_id = task['id']
        if self.active_timer:
            self.active_timer['start_time'] = datetime.now().isoformat()
            self.active_timer['task_id'] = task['id']
        else:
            self.active_timer = {
                'task_id': task['id'],
                'start_time': datetime.now().isoformat(),
                'elapsed': 0
            }
        
        self.is_timer_running = True
        self.last_tick_time = datetime.now()
        self.update_play_btn_icon()
        self.stop_btn.set_sensitive(True)
        self.timer_combo.set_sensitive(False)
        self.start_timer_loop()
        self.save_state()
    
    def pause_timer(self):
        """Pause timer."""
        if self.timer_source_id:
            GLib.source_remove(self.timer_source_id)
            self.timer_source_id = None
        
        if self.active_timer and self.active_timer.get('start_time'):
            start = datetime.fromisoformat(self.active_timer['start_time'])
            self.active_timer['elapsed'] += (datetime.now() - start).total_seconds()
            self.active_timer['start_time'] = None
        
        self.is_timer_running = False
        self.last_tick_time = None
        self.update_play_btn_icon()
        self.timer_combo.set_sensitive(True)
        self.refresh_timer_display()
        self.save_state()
    
    def stop_timer(self):
        """Stop timer and log time."""
        # Stop the timer loop first
        if self.timer_source_id:
            GLib.source_remove(self.timer_source_id)
            self.timer_source_id = None
        
        if self.active_timer:
            # Calculate duration
            elapsed = max(0, self.active_timer.get('elapsed', 0))
            start_dt = None
            if self.active_timer.get('start_time'):
                try:
                    start_dt = datetime.fromisoformat(self.active_timer['start_time'])
                    elapsed += max(0, (datetime.now() - start_dt).total_seconds())
                except (ValueError, TypeError):
                    pass
            if start_dt is None:
                start_dt = datetime.now() - timedelta(seconds=elapsed)
            end_dt = start_dt + timedelta(seconds=max(0, elapsed))
            
            # Clamp absurdly long sessions
            max_session_sec = 16 * 3600
            elapsed = min(elapsed, max_session_sec)

            # Log time if any elapsed, splitting across days to keep dates accurate
            if elapsed > 1:  # ignore sub-second blips
                remaining = max(0, elapsed)
                cur_start = start_dt
                while cur_start.date() < end_dt.date():
                    day_end = datetime.combine(cur_start.date() + timedelta(days=1), datetime.min.time())
                    seg_dur = (day_end - cur_start).total_seconds()
                    self.time_logs.append({
                        'task_id': self.active_timer['task_id'],
                        'start': cur_start.isoformat(),
                        'end': day_end.isoformat(),
                        'duration': seg_dur
                    })
                    remaining -= seg_dur
                    cur_start = day_end
                if remaining > 0:
                    self.time_logs.append({
                        'task_id': self.active_timer['task_id'],
                        'start': cur_start.isoformat(),
                        'end': end_dt.isoformat(),
                        'duration': remaining
                    })
        
        # Reset everything
        self.active_timer = None
        self.is_timer_running = False
        self.timer_display.set_label("0:00")
        self.update_play_btn_icon()
        self.stop_btn.set_sensitive(False)
        self.timer_combo.set_sensitive(True)
        
        self.refresh_tasks()
        self.refresh_chart()
        self.refresh_calendar()
        self.save_state()
    
    def start_timer_loop(self):
        """Start timer update loop."""
        if self.timer_source_id:
            GLib.source_remove(self.timer_source_id)
            self.timer_source_id = None
        self.last_tick_time = datetime.now()
        
        def tick():
            if not self.active_timer:
                return False
            now = datetime.now()
            elapsed = self.active_timer.get('elapsed', 0)
            if self.active_timer.get('start_time'):
                try:
                    start = datetime.fromisoformat(self.active_timer['start_time'])
                    elapsed += (now - start).total_seconds()
                except (ValueError, TypeError):
                    pass
            # Detect long idle/sleep gaps and clamp contribution
            if self.last_tick_time:
                gap = (now - self.last_tick_time).total_seconds()
                idle_cap = 3600  # cap one hour of unattended time per gap
                if gap > idle_cap:
                    # Move start_time forward to trim unintended accumulation
                    if self.active_timer.get('start_time'):
                        try:
                            new_start = now - timedelta(seconds=idle_cap)
                            self.active_timer['start_time'] = new_start.isoformat()
                            # Recompute elapsed with cap applied
                            elapsed = self.active_timer.get('elapsed', 0)
                            elapsed += idle_cap
                            try:
                                self.send_notification('Tracker paused gap trimmed', f'Idle gap of {int(gap//60)}m capped to 60m')
                            except Exception:
                                pass
                        except Exception:
                            pass
                    self.last_tick_time = now
                else:
                    self.last_tick_time = now
            else:
                self.last_tick_time = now
            mins = int(elapsed // 60)
            secs = int(elapsed % 60)
            self.timer_display.set_label(f"{mins}:{secs:02d}")
            return True
        
        self.timer_source_id = GLib.timeout_add_seconds(1, tick)
        tick()  # Update immediately

    def refresh_timer_display(self):
        """Update timer label based on current timer state."""
        if not self.active_timer:
            self.timer_display.set_label("0:00")
            return
        elapsed = self.active_timer.get('elapsed', 0)
        if self.active_timer.get('start_time'):
            try:
                start = datetime.fromisoformat(self.active_timer['start_time'])
                elapsed += (datetime.now() - start).total_seconds()
            except (ValueError, TypeError):
                pass
        mins = int(elapsed // 60)
        secs = int(elapsed % 60)
        self.timer_display.set_label(f"{mins}:{secs:02d}")
    
    # === Reminder Functions ===
    def refresh_reminders(self):
        """Refresh reminders display."""
        for c in self.reminders_box.get_children():
            self.reminders_box.remove(c)
        
        for r in self.reminders:
            row = self.make_reminder_row(r)
            self.reminders_box.add(row)
        self.reminders_box.show_all()
    
    def make_reminder_row(self, rem):
        """Create reminder row."""
        row = Box(name="tracker-reminder-row", orientation="h", spacing=6)

        name = Label(name="tracker-reminder-name", label=rem['name'], h_expand=True)
        name.set_xalign(0)
        row.add(name)

        buttonAndTime =Box(name="tracker-reminder-button-time", orientation="h", spacing=8)
        
        # Enable/disable toggle icon (bell)
        toggle_icon = icons.notifications if rem.get('enabled', True) else icons.notifications_off
        toggle_btn = Button(name="tracker-reminder-toggle", child=Label(markup=toggle_icon))
        toggle_btn.connect("clicked", lambda w, r=rem['id']: self.toggle_reminder(r))
        buttonAndTime.add(toggle_btn)

        # Time and countdown
        hours = rem['time_hours']
        h = int(hours)
        m = int((hours - h) * 60)
        time_str = f"{h}:{m:02d}"
        time = Label(name="tracker-reminder-time", label=time_str)
        # row.add(time)

        next_fire = self.get_next_fire_datetime(rem)
        countdown = self.get_time_left_display(next_fire)
        nf_label = Label(name="tracker-reminder-next", label=countdown, h_expand=True)
        nf_label.set_xalign(0)
        buttonAndTime.add(nf_label)

        rid = rem['id']
        del_btn = Button(name="tracker-reminder-delete", child=Label(markup=icons.cancel))
        del_btn.connect("clicked", lambda w, r=rid: self.del_reminder(r))
        buttonAndTime.add(del_btn)

        row.add(buttonAndTime)
        return row

    def send_notification(self, title, body):
        """Fire a desktop notification in a non-blocking way and play a sound if possible."""
        # Send desktop notification
        try:
            subprocess.Popen(
                ['notify-send', title, body],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                start_new_session=True
            )
        except Exception:
            pass
        # Try to play a short sound without blocking (best-effort)
        try:
            # Prefer canberra theme sounds if available
            subprocess.Popen(
                ['bash', '-lc', "command -v canberra-gtk-play >/dev/null 2>&1 && canberra-gtk-play -i message-new-instant || true"],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                start_new_session=True
            )
        except Exception:
            pass

    def export_time_logs_json(self):
        """Export time logs to ~/.tracker_time_logs.json with task names."""
        out_path = Path(os.path.expanduser("~/.tracker_time_logs.json"))
        tmp_path = out_path.with_suffix('.tmp')
        task_lookup = {t['id']: t['name'] for t in self.tasks}
        payload = []
        for log in self.time_logs:
            record = dict(log)
            record['task_name'] = task_lookup.get(log.get('task_id'), 'Unknown')
            payload.append(record)
        try:
            with open(tmp_path, 'w') as f:
                json.dump(payload, f, indent=2)
                f.flush()
                os.fsync(f.fileno())
            tmp_path.replace(out_path)
            self.send_notification('Tracker export', f'JSON written to {out_path}')
        except Exception as e:
            print(f"Export JSON error: {e}")

    def export_time_logs_csv(self):
        """Export time logs to ~/.tracker_time_logs.csv with task names."""
        out_path = Path(os.path.expanduser("~/.tracker_time_logs.csv"))
        tmp_path = out_path.with_suffix('.tmp')
        task_lookup = {t['id']: t['name'] for t in self.tasks}
        try:
            with open(tmp_path, 'w') as f:
                f.write('task_id,task_name,start,end,duration_seconds\n')
                for log in self.time_logs:
                    task_name = task_lookup.get(log.get('task_id'), 'Unknown')
                    start = log.get('start', '')
                    end = log.get('end', '')
                    duration = log.get('duration', 0)
                    # Simple CSV escaping for commas by quoting
                    def esc(val):
                        if val is None:
                            return ''
                        s = str(val)
                        if ',' in s or '"' in s:
                            s = '"' + s.replace('"', '""') + '"'
                        return s
                    f.write(f"{esc(log.get('task_id'))},{esc(task_name)},{esc(start)},{esc(end)},{duration}\n")
                f.flush()
                os.fsync(f.fileno())
            tmp_path.replace(out_path)
            self.send_notification('Tracker export', f'CSV written to {out_path}')
        except Exception as e:
            print(f"Export CSV error: {e}")
    
    def parse_time_input(self, time_str):
        """Parse time input - accepts 'h:mm', 'h.h', or bare minutes."""
        time_str = time_str.strip()
        if ':' in time_str:
            # Format: h:mm or mm:ss
            parts = time_str.split(':')
            try:
                h = int(parts[0])
                m = int(parts[1]) if len(parts) > 1 else 0
                return h + m / 60.0
            except ValueError:
                return None
        else:
            # Treat bare numbers as minutes for consistency with the placeholder
            try:
                minutes = float(time_str)
                return minutes / 60.0
            except ValueError:
                return None
    
    def add_reminder(self):
        """Add new reminder."""
        name = self.reminder_entry.get_text().strip()
        time_str = self.reminder_time.get_text().strip()
        if not name or not time_str:
            return
        
        hours = self.parse_time_input(time_str)
        if hours is None:
            self.send_notification('Invalid time', "Use h:mm, h.h, or minutes")
            return

        # Determine if this is a relative countdown (e.g., 0:05 or bare minutes) vs daily time-of-day
        is_relative = False
        if ':' in time_str:
            first_part = time_str.split(':', 1)[0].strip()
            if first_part in ('', '0', '00'):
                is_relative = True
        else:
            is_relative = True  # bare numbers treated as minutes from now
        
        rid = max([r['id'] for r in self.reminders], default=0) + 1
        self.reminders.append({
            'id': rid,
            'name': name,
            'time_hours': hours,
            'created': datetime.now().isoformat(),
            'enabled': True,
            'snoozed_until': None,
            'sound': False,
            'is_relative': is_relative,
            'next_fire_at': None
        })
        self.reminder_entry.set_text("")
        self.reminder_time.set_text("")
        self.refresh_reminders()
        self.schedule_reminder(self.reminders[-1])
        self.save_state()
    
    def del_reminder(self, rid):
        """Delete reminder."""
        self.reminders = [r for r in self.reminders if r['id'] != rid]
        self.cancel_reminder_timer(rid)
        self.refresh_reminders()
        self.save_state()

    def toggle_reminder(self, rid):
        """Enable/disable a reminder without deleting it."""
        for r in self.reminders:
            if r['id'] == rid:
                r['enabled'] = not r.get('enabled', True)
                if r['enabled']:
                    self.schedule_reminder(r)
                else:
                    self.cancel_reminder_timer(rid)
                break
        self.refresh_reminders()
        self.save_state()

    def snooze_reminder(self, rid, minutes=10):
        """Snooze a reminder for a short delay."""
        for r in self.reminders:
            if r['id'] == rid:
                r['snoozed_until'] = (datetime.now() + timedelta(minutes=minutes)).isoformat()
                self.schedule_reminder(r)
                break
        self.refresh_reminders()
        self.save_state()

    def dismiss_reminder(self, rid):
        """Dismiss once: clear snooze and schedule next regular occurrence."""
        for r in self.reminders:
            if r['id'] == rid:
                r['snoozed_until'] = None
                self.schedule_reminder(r)
                break
        self.refresh_reminders()
        self.save_state()

    def cancel_reminder_timer(self, rid):
        """Cancel a scheduled reminder by id."""
        timer_id = self.reminder_source_ids.pop(rid, None)
        if timer_id:
            GLib.source_remove(timer_id)

    def cancel_all_reminder_timers(self):
        """Cancel all scheduled reminders."""
        for timer_id in self.reminder_source_ids.values():
            GLib.source_remove(timer_id)
        self.reminder_source_ids = {}

    def schedule_reminder(self, rem):
        """Schedule a daily reminder at the specified time-of-day."""
        if not rem.get('enabled', True):
            self.cancel_reminder_timer(rem['id'])
            return
        self.cancel_reminder_timer(rem['id'])
        now = datetime.now()

        # Snooze takes precedence if in the future
        snoozed_until = rem.get('snoozed_until')
        if snoozed_until:
            try:
                snooze_dt = datetime.fromisoformat(snoozed_until)
            except Exception:
                snooze_dt = None
        else:
            snooze_dt = None

        # Use a stored next_fire_at when it is still in the future to keep countdown stable across restarts
        stored_target = None
        nfa = rem.get('next_fire_at')
        if nfa:
            try:
                nfa_dt = datetime.fromisoformat(nfa)
                if nfa_dt > now:
                    stored_target = nfa_dt
            except Exception:
                stored_target = None

        if rem.get('is_relative'):
            base_target = now + timedelta(hours=rem['time_hours'])
        else:
            base_target = datetime.combine(now.date(), datetime.min.time()) + timedelta(hours=rem['time_hours'])
            if base_target <= now:
                base_target += timedelta(days=1)

        target = None
        if snooze_dt and snooze_dt > now:
            target = snooze_dt
        elif stored_target:
            target = stored_target
        else:
            target = base_target
            rem['snoozed_until'] = None

        rem['next_fire_at'] = target.isoformat()
        delay_ms = max(1000, int((target - now).total_seconds() * 1000))

        def fire():
            self.send_notification('Reminder', rem['name'])
            # Reschedule for the next interval/next day after firing
            rem['snoozed_until'] = None
            rem['next_fire_at'] = None
            self.schedule_reminder(rem)
            self.refresh_reminders()
            return False

        timer_id = GLib.timeout_add(delay_ms, fire)
        self.reminder_source_ids[rem['id']] = timer_id

    def schedule_all_reminders(self):
        """(Re)schedule all reminders from current state."""
        self.cancel_all_reminder_timers()
        for rem in self.reminders:
            self.schedule_reminder(rem)

    def get_next_fire_datetime(self, rem):
        """Compute next planned fire time for display."""
        if not rem.get('enabled', True):
            return None
        now = datetime.now()
        snoozed_until = rem.get('snoozed_until')
        snooze_dt = None
        if snoozed_until:
            try:
                snooze_dt = datetime.fromisoformat(snoozed_until)
            except Exception:
                snooze_dt = None
        if snooze_dt and snooze_dt > now:
            return snooze_dt
        # Prefer stored next_fire_at
        nfa = rem.get('next_fire_at')
        if nfa:
            try:
                nfa_dt = datetime.fromisoformat(nfa)
                if nfa_dt > now:
                    return nfa_dt
            except Exception:
                pass
        # Fallback calculations
        if rem.get('is_relative'):
            return now + timedelta(hours=rem['time_hours'])
        target = datetime.combine(now.date(), datetime.min.time()) + timedelta(hours=rem['time_hours'])
        if target <= now:
            target += timedelta(days=1)
        return target

    def get_time_left_display(self, target_dt):
        """Return human friendly time-until string."""
        if not target_dt:
            return "—"
        delta = target_dt - datetime.now()
        total_sec = max(0, int(delta.total_seconds()))
        hours = total_sec // 3600
        minutes = (total_sec % 3600) // 60
        seconds = total_sec % 60
        return f"{hours:02d}:{minutes:02d}:{seconds:02d}"

    def start_reminder_tick_loop(self):
        """Periodically refresh reminder display to keep time-left current."""
        if self.reminder_tick_id:
            GLib.source_remove(self.reminder_tick_id)
            self.reminder_tick_id = None

        def tick():
            self.refresh_reminders()
            return True

        self.reminder_tick_id = GLib.timeout_add_seconds(1, tick)
    
    # === Chart Functions ===
    def get_theme_color(self, widget, color_name="primary"):
        """Get theme color from widget style context."""
        style = widget.get_style_context()
        # Theme colors with accent variations
        defaults = {
            'primary': (1.0, 0.718, 0.525),      # #ffb786 - warm orange
            'secondary': (0.898, 0.749, 0.659),  # #e5bfa8
            'surface': (0.098, 0.071, 0.051),    # #19120d
            'surface_bright': (0.255, 0.216, 0.192),  # #413731
            'outline': (0.624, 0.553, 0.514),    # #9f8d83
            'foreground': (0.941, 0.875, 0.843), # #f0dfd7
            'green': (0.718, 0.816, 0.522),      # #b7d085
            'cyan': (0.518, 0.835, 0.769),       # #84d5c4
            'tertiary': (0.788, 0.792, 0.576),   # #c9ca93
        }
        return defaults.get(color_name, (1.0, 0.718, 0.525))
    
    def draw_spline_chart(self, widget, cr):
        """Draw a smooth spline chart for weekly data using theme colors."""
        w = widget.get_allocated_width()
        h = widget.get_allocated_height()
        
        if w < 10 or h < 10:
            return False
        
        # Get theme colors
        primary = self.get_theme_color(widget, 'primary')
        secondary = self.get_theme_color(widget, 'secondary')
        outline = self.get_theme_color(widget, 'outline')
        surface = self.get_theme_color(widget, 'surface')
        surface_bright = self.get_theme_color(widget, 'surface_bright')
        fg = self.get_theme_color(widget, 'foreground')
        tertiary = self.get_theme_color(widget, 'tertiary')
        
        # Get week data
        today = datetime.now().date()
        data = []
        day_names = []
        for i in range(7):
            day = today - timedelta(days=6-i)
            hrs = sum(log['duration']/3600 for log in self.time_logs
                      if datetime.fromisoformat(log['start']).date() == day)
            data.append(hrs)
            day_names.append(day.strftime('%a')[0])  # M, T, W, etc.
        
        # Compact padding
        pad_left = 25
        pad_right = 10
        pad_top = 10
        pad_bottom = 20
        
        chart_w = w - pad_left - pad_right
        chart_h = h - pad_top - pad_bottom
        
        if chart_w < 10 or chart_h < 10:
            return False
        
        max_val = max(data) if data and max(data) > 0 else 1
        
        # Draw grid lines (subtle)
        cr.set_source_rgba(outline[0], outline[1], outline[2], 0.2)
        cr.set_line_width(1)
        for i in range(4):
            y = pad_top + (i / 3) * chart_h
            cr.move_to(pad_left, y)
            cr.line_to(w - pad_right, y)
            cr.stroke()
        
        # Draw Y-axis labels
        cr.set_source_rgba(outline[0], outline[1], outline[2], 0.8)
        cr.set_font_size(8)
        for i in range(4):
            val = max_val * (3 - i) / 3
            y = pad_top + (i / 3) * chart_h + 3
            cr.move_to(3, y)
            cr.show_text(f"{int(val * 60)}m")
        
        # Calculate points
        points = []
        step = chart_w / 6 if len(data) > 1 else chart_w
        for i, hrs in enumerate(data):
            x = pad_left + i * step
            y = pad_top + chart_h - (hrs / max_val) * chart_h
            points.append((x, y))
        
        # Draw filled area under curve with gradient
        if len(points) >= 2:
            cr.move_to(points[0][0], pad_top + chart_h)
            cr.line_to(points[0][0], points[0][1])
            
            # Draw Catmull-Rom spline
            for i in range(len(points) - 1):
                p0 = points[max(0, i - 1)]
                p1 = points[i]
                p2 = points[min(len(points) - 1, i + 1)]
                p3 = points[min(len(points) - 1, i + 2)]
                
                cp1x = p1[0] + (p2[0] - p0[0]) / 6
                cp1y = p1[1] + (p2[1] - p0[1]) / 6
                cp2x = p2[0] - (p3[0] - p1[0]) / 6
                cp2y = p2[1] - (p3[1] - p1[1]) / 6
                
                cr.curve_to(cp1x, cp1y, cp2x, cp2y, p2[0], p2[1])
            
            cr.line_to(points[-1][0], pad_top + chart_h)
            cr.close_path()
            
            # Create vertical gradient for fill
            import cairo
            gradient = cairo.LinearGradient(0, pad_top, 0, pad_top + chart_h)
            gradient.add_color_stop_rgba(0, primary[0], primary[1], primary[2], 0.35)
            gradient.add_color_stop_rgba(0.5, secondary[0], secondary[1], secondary[2], 0.15)
            gradient.add_color_stop_rgba(1, primary[0], primary[1], primary[2], 0.02)
            cr.set_source(gradient)
            cr.fill()
        
        # Draw the spline line (theme primary with glow effect)
        if len(points) >= 2:
            # Draw glow (thicker, more transparent)
            cr.set_source_rgba(primary[0], primary[1], primary[2], 0.3)
            cr.set_line_width(5)
            
            cr.move_to(points[0][0], points[0][1])
            
            for i in range(len(points) - 1):
                p0 = points[max(0, i - 1)]
                p1 = points[i]
                p2 = points[min(len(points) - 1, i + 1)]
                p3 = points[min(len(points) - 1, i + 2)]
                
                cp1x = p1[0] + (p2[0] - p0[0]) / 6
                cp1y = p1[1] + (p2[1] - p0[1]) / 6
                cp2x = p2[0] - (p3[0] - p1[0]) / 6
                cp2y = p2[1] - (p3[1] - p1[1]) / 6
                
                cr.curve_to(cp1x, cp1y, cp2x, cp2y, p2[0], p2[1])
            
            cr.stroke()
            
            # Draw main line
            cr.set_source_rgba(primary[0], primary[1], primary[2], 1.0)
            cr.set_line_width(2.5)
            
            cr.move_to(points[0][0], points[0][1])
            
            for i in range(len(points) - 1):
                p0 = points[max(0, i - 1)]
                p1 = points[i]
                p2 = points[min(len(points) - 1, i + 1)]
                p3 = points[min(len(points) - 1, i + 2)]
                
                cp1x = p1[0] + (p2[0] - p0[0]) / 6
                cp1y = p1[1] + (p2[1] - p0[1]) / 6
                cp2x = p2[0] - (p3[0] - p1[0]) / 6
                cp2y = p2[1] - (p3[1] - p1[1]) / 6
                
                cr.curve_to(cp1x, cp1y, cp2x, cp2y, p2[0], p2[1])
            
            cr.stroke()
        
        # Draw data points with glow effect
        for x, y in points:
            # Outer glow
            cr.set_source_rgba(primary[0], primary[1], primary[2], 0.3)
            cr.arc(x, y, 6, 0, 2 * math.pi)
            cr.fill()
            # Main circle
            cr.set_source_rgba(primary[0], primary[1], primary[2], 1.0)
            cr.arc(x, y, 4, 0, 2 * math.pi)
            cr.fill()
            # Inner highlight
            cr.set_source_rgba(fg[0], fg[1], fg[2], 0.9)
            cr.arc(x, y, 2, 0, 2 * math.pi)
            cr.fill()
        
        # Draw day labels (theme primary)
        cr.set_source_rgba(primary[0], primary[1], primary[2], 0.9)
        cr.set_font_size(8)
        for i, name in enumerate(day_names):
            x = pad_left + i * step - 3
            cr.move_to(x, h - 5)
            cr.show_text(name)
        
        return False
    
    def refresh_chart(self):
        """Refresh chart."""
        if hasattr(self, 'chart_area'):
            self.chart_area.queue_draw()
    
    # === Calendar Functions ===
    def refresh_calendar(self):
        """Refresh monthly calendar with proper calendar layout."""
        for c in self.calendar_grid.get_children():
            self.calendar_grid.remove(c)
        
        today = datetime.now()
        year = today.year
        month = today.month
        
        # Get month data - which days have logged time
        month_hrs = {}
        for log in self.time_logs:
            try:
                d = datetime.fromisoformat(log['start']).date()
                if d.year == year and d.month == month:
                    month_hrs[d.day] = month_hrs.get(d.day, 0) + log['duration']/3600
            except (ValueError, KeyError):
                pass
        
        # Day headers (Mon-Sun)
        day_headers = ['Mo', 'Tu', 'We', 'Th', 'Fr', 'Sa', 'Su']
        for i, d in enumerate(day_headers):
            lbl = Label(name="tracker-month-header", label=d)
            self.calendar_grid.attach(lbl, i, 0, 1, 1)
        
        # Get first day of month (0=Monday, 6=Sunday)
        first_day_weekday = cal.monthrange(year, month)[0]
        days_in_month = cal.monthrange(year, month)[1]
        
        # Fill calendar grid
        row = 1
        col = first_day_weekday
        
        for day in range(1, days_in_month + 1):
            if day in month_hrs:
                lbl = Label(name="tracker-month-day-active", label=str(day))
                # Format tooltip with hours and minutes
                hrs = month_hrs[day]
                h = int(hrs)
                m = int((hrs - h) * 60)
                tooltip = f"{h}h {m}m worked"
                lbl.set_tooltip_text(tooltip)
            elif day == today.day:
                lbl = Label(name="tracker-month-day-today", label=str(day))
                lbl.set_tooltip_text("Today")
            else:
                lbl = Label(name="tracker-month-day", label=str(day))
            
            self.calendar_grid.attach(lbl, col, row, 1, 1)
            
            col += 1
            if col > 6:
                col = 0
                row += 1
        
        self.calendar_grid.show_all()
    
    # === State Management ===
    def save_state(self):
        """Save state to file."""
        data = {
            'tasks': self.tasks,
            'time_logs': self.time_logs,
            'reminders': self.reminders,
            'active_timer': self.active_timer,
            'next_task_id': self.next_task_id,
            'selected_task_id': self.selected_task_id
        }
        tmp_path = self.STATE_FILE.with_suffix('.tmp')
        backup_path = self.STATE_FILE.with_suffix('.bak')
        try:
            if self.STATE_FILE.exists():
                try:
                    shutil.copy2(self.STATE_FILE, backup_path)
                except Exception:
                    pass
            with open(tmp_path, 'w') as f:
                json.dump(data, f, indent=2)
                f.flush()
                os.fsync(f.fileno())
            tmp_path.replace(self.STATE_FILE)
        except Exception as e:
            print(f"Save error: {e}")
    
    def load_state(self):
        """Load state from file."""
        if not self.STATE_FILE.exists():
            return
        try:
            with open(self.STATE_FILE) as f:
                data = json.load(f)
                self._apply_loaded_state(data)
        except Exception as e:
            notify_path = None
            try:
                corrupt_path = self.STATE_FILE.with_suffix('.corrupt')
                timestamped = corrupt_path.with_name(corrupt_path.stem + f"-{int(datetime.now().timestamp())}" + corrupt_path.suffix)
                self.STATE_FILE.replace(timestamped)
                notify_path = str(timestamped)
            except Exception:
                pass
            print(f"Load error: {e}")
            try:
                if notify_path:
                    self.send_notification('Tracker data quarantined', f'Corrupt state moved to\n{notify_path}')
            except Exception:
                pass

    def _apply_loaded_state(self, data):
        """Validate and apply loaded state safely."""
        if not isinstance(data, dict):
            return
        tasks = []
        for t in data.get('tasks', []) if isinstance(data.get('tasks', []), list) else []:
            if isinstance(t, dict) and {'id', 'name', 'units', 'done'} <= set(t.keys()):
                t.setdefault('archived', False)
                t.setdefault('is_today', True)
                tasks.append(t)
        time_logs = []
        for log in data.get('time_logs', []) if isinstance(data.get('time_logs', []), list) else []:
            if isinstance(log, dict) and {'task_id', 'start', 'duration'} <= set(log.keys()):
                time_logs.append(log)
        reminders = []
        for r in data.get('reminders', []) if isinstance(data.get('reminders', []), list) else []:
            if isinstance(r, dict) and {'id', 'name', 'time_hours'} <= set(r.keys()):
                r.setdefault('enabled', True)
                r.setdefault('snoozed_until', None)
                r.setdefault('sound', False)
                r.setdefault('is_relative', False)
                r.setdefault('next_fire_at', None)
                reminders.append(r)
        self.tasks = tasks
        self.time_logs = time_logs
        self.reminders = reminders
        self.active_timer = data.get('active_timer') if isinstance(data.get('active_timer'), dict) else None
        self.next_task_id = data.get('next_task_id', 1)
        self.selected_task_id = data.get('selected_task_id') if isinstance(data.get('selected_task_id'), int) else None
        if self.tasks:
            max_id = max(t['id'] for t in self.tasks)
            self.next_task_id = max(self.next_task_id, max_id + 1)
