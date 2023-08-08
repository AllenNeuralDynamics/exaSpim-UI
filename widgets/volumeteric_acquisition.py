from widgets.widget_base import WidgetBase
from qtpy.QtWidgets import QPushButton, QCheckBox, QLabel, QComboBox, QSpinBox, QDockWidget, \
    QSlider, QLineEdit,QMessageBox, QTabWidget, QProgressBar
import numpy as np
from pyqtgraph import PlotWidget, mkPen
from exaspim.operations.waveform_generator import generate_waveforms
import logging
from napari.qt.threading import thread_worker, create_worker
from time import sleep
import qtpy.QtCore as QtCore
from datetime import timedelta, datetime
import calendar

class VolumetericAcquisition(WidgetBase):

    def __init__(self,viewer, cfg, instrument, simulated):

        """
            :param viewer: napari viewer
            :param cfg: config object from instrument
            :param instrument: instrument bing used
            :param simulated: if instrument is in simulate mode
        """

        self.log = logging.getLogger(__name__ + "." + self.__class__.__name__)

        self.cfg = cfg
        self.viewer = viewer
        self.instrument = instrument
        self.simulated = simulated

        self.waveform = {}
        self.selected = {}
        self.progress = {}
        self.data_line = None       # Lines for graph
        self.limits = {}

    def set_tab_widget(self, tab_widget: QTabWidget):

        self.tab_widget = tab_widget

    def volumeteric_imaging_button(self):

        self.volumetric_image = {'start': QPushButton('Start Volumetric Imaging'),
                                 'overwrite': QCheckBox('Overwrite')}
        self.volumetric_image['start'].clicked.connect(self.run_volumeteric_imaging)
        # Put in seperate function so upon initiation of gui, run() funtion does not start

        return self.create_layout(struct='H', **self.volumetric_image)

    def run_volumeteric_imaging(self):

        if self.volumetric_image['overwrite'].isChecked():
            return_value = self.overwrite_warning()
            if return_value == QMessageBox.Cancel:
                return
        return_value = self.scan_summary()
        if return_value == QMessageBox.Cancel:
            return

        for i in range(1,len(self.tab_widget)):
            self.tab_widget.setTabEnabled(i,False)
        self.instrument.cfg.save()
        self.run_worker = self._run()
        self.run_worker.finished.connect(lambda: self.end_scan())  # Napari threads have finished signals
        self.run_worker.start()
        sleep(5)
        self.volumetric_image_worker = create_worker(self.instrument._livestream_worker)
        self.volumetric_image_worker.yielded.connect(self.update_layer)
        self.volumetric_image_worker.start()

        sleep(5)
        self.progress_worker = self._progress_bar_worker()
        self.progress_worker.start()

    @thread_worker
    def _run(self):
        self.instrument.run(overwrite=self.volumetric_image['overwrite'].isChecked(), spim_name='exaSPIM')
        yield


    def end_scan(self):

        self.run_worker.quit()
        self.volumetric_image_worker.quit()
        self.viewer.layers.clear()      # Gui crashes if you zoom in on last uploaded image.
        # Maybe also just upload the most downsampled image as solution?

    def progress_bar_widget(self):

        self.progress['bar'] = QProgressBar()
        self.progress['bar'].setStyleSheet('QProgressBar::chunk {background-color: green;}')
        self.progress['bar'].setHidden(True)

        self.progress['end_time'] = QLabel()
        self.progress['end_time'].setHidden(True)

        return self.create_layout(struct='H', **self.progress)

    @thread_worker
    def _progress_bar_worker(self):
        """Displays progress bar of the current scan"""

        QtCore.QMetaObject.invokeMethod(self.progress['bar'], 'setHidden', QtCore.Q_ARG(bool, False))
        QtCore.QMetaObject.invokeMethod(self.progress['end_time'], 'setHidden', QtCore.Q_ARG(bool, False))
        QtCore.QMetaObject.invokeMethod(self.progress['bar'], 'setValue', QtCore.Q_ARG(int, 0))
        while self.instrument.total_tiles == 0:
            sleep(.5)       # Stall since the following meterics won't be calculated yet
        total_tiles = self.instrument.total_tiles
        z_tiles = total_tiles / self.instrument.x_y_tiles
        time_scale = self.instrument.x_y_tiles/86400
        est_run_time = ((((self.cfg.get_channel_cycle_time(488))) * z_tiles)    # Kinda hacky if cycle times are different
                        *self.instrument.x_y_tiles)/86400    # Needs to be a base class thing

        pct = 0
        while self.instrument.acquiring_images:
            pct = self.instrument.frame_index/total_tiles if self.instrument.frame_index != 0 else pct
            QtCore.QMetaObject.invokeMethod(self.progress['bar'], f'setValue', QtCore.Q_ARG(int, round(pct*100)))
            # Qt threads are so weird. Can't invoke repaint method outside of main thread and Qthreads don't play nice
            # with napari threads so QMetaObject is static read-only instances

            if self.instrument.curr_tile_index == 0:
                completion_date = self.instrument.start_time + timedelta(days=est_run_time)

            else:
                total_time_days = self.instrument.tile_time_s*time_scale
                completion_date = self.instrument.start_time + timedelta(days=total_time_days)

            date_str = completion_date.strftime("%d %b, %Y at %H:%M %p")
            weekday = calendar.day_name[completion_date.weekday()]
            self.progress['end_time'].setText(f"End Time: {weekday}, {date_str}")
            sleep(.5)
            yield  # So thread can stop

    def scan_summary(self):

        x, y, z = self.instrument.get_tile_counts(self.cfg.tile_overlap_x_percent,
                                                           self.cfg.tile_overlap_y_percent,
                                                           self.cfg.z_step_size_um,
                                                           self.cfg.volume_x_um,
                                                           self.cfg.volume_y_um,
                                                           self.cfg.volume_z_um)
        est_run_time = ((((self.cfg.get_channel_cycle_time(488))) * z)  # Kinda hacky if cycle times are different
                        * (x*y)) / 86400
        msgBox = QMessageBox()
        msgBox.setIcon(QMessageBox.Information)
        msgBox.setText(f"Scan Summary\n"
                       f"Lasers: {self.cfg.channels}\n"
                       f"Time: {round(est_run_time, 3)} days\n"
                       f"X Tiles: {x}\n"
                       f"Y Tiles: {y}\n"
                       f"Z Tiles: {z}\n"
                       f"Local Dir: {self.cfg.local_storage_dir}\n"
                       f"External Dir: {self.cfg.ext_storage_dir}\n"
                       f"Press cancel to abort run")
        msgBox.setWindowTitle("Scan Summary")
        msgBox.setStandardButtons(QMessageBox.Ok | QMessageBox.Cancel)
        return msgBox.exec()

    def overwrite_warning(self):
        msgBox = QMessageBox()
        msgBox.setIcon(QMessageBox.Information)
        msgBox.setText("Running Acquisition will overwrite files. Are you sure you want to do this?")
        msgBox.setWindowTitle("Overwrite Files")
        msgBox.setStandardButtons(QMessageBox.Ok | QMessageBox.Cancel)
        return msgBox.exec()

    def waveform_graph(self):

        """Generate a graph of waveforms for sanity check"""

        # TODO: change colors and make it a different pop up window. As of now it will interfere with widget placement
        self.waveform['generate'] = QPushButton('Generate Waveforms')
        self.colors = np.random.randint(0, 255,
                                        [12, 3])  # rework this so the colors are set and laser colors are consistent
        self.waveform['graph'] = PlotWidget()
        self.waveform['generate'].clicked.connect(self.waveform_update)

        return self.waveform['generate']

    def waveform_update(self):

        """Update graph with new waveforms"""

        voltages_t = generate_waveforms(self.cfg, channels =self.cfg.channels)      # Generate waveforms based on cfg
        t = np.linspace(0, self.cfg.daq_period_time, len(voltages_t[0]), endpoint=False)    # Calculate time

        # Cycle through indexes and ao channels names to add lines and legend to graph
        for index, ao_name in enumerate(self.cfg.n2c.keys()):
            self.waveform['graph'].addLegend(offset=(365, .5), horSpacing=20, verSpacing=0, labelTextSize='8pt')
            self.waveform['graph'].plot(t, voltages_t[index], name=ao_name,
                                        pen=mkPen(color=self.colors[index], width=3))

        # Remove previous graph if present and add new graph
        try:
            self.viewer.window.remove_dock_widget(self.waveform['graph'])
        except LookupError:
            pass
        finally:
            self.viewer.window.add_dock_widget(self.waveform['graph'])

    def limit_tab(self):

        """Create tab to set limits on exaspim"""

        directions = ['x', 'y', 'z']
        self.min_max_widgets = {}

        self.min_max_widgets['min_limit'] = QLabel('Minimum Limits')
        self.min_max_widgets['max_limit'] = QLabel('Maximum Limits')
        for direction in directions:
            self.limits[f'{direction}min'] = None
            self.limits[f'{direction}max'] = None

            self.min_max_widgets[direction] = QPushButton(f'{direction} min limit')
            self.min_widgets[direction].clicked.connect(lambda direction=direction, extreme='min':self.set_limit(direction, extreme))
            self.min_widgets[direction + 'label'] = QLabel(':')

            self.max_widgets[direction] = QPushButton(f'{direction} max limit')
            self.max_widgets[direction + 'label'] = QLabel(':')
            self.min_widgets[direction].clicked.connect(
                lambda direction=direction, extreme='max': self.set_limit(direction, extreme))

        calculate = QPushButton('Calculate Position')
        calculate.setDisabled(True)

    def set_limit(self, direction, extreme):

        """Set min and max limits for x, y, z"""

        widget = self.min_widgets[direction + 'label'] if extreme == 'min' else self.max_widgets[direction + 'label']
        position = self.instrument.sample_pose.get_position(direction)
        widget.setText(f': {position[direction]/10} um')
        self.limits[f'{direction}{extreme}'] = position[direction]
        if None not in self.limits.values():
            calculate.setDisabled(True)




