from widgets.widget_base import WidgetBase
from qtpy.QtWidgets import QPushButton, QCheckBox, QLabel, QComboBox, QSpinBox, QDockWidget, \
    QSlider, QLineEdit,QMessageBox, QTabWidget
import numpy as np
from pyqtgraph import PlotWidget, mkPen
from exaspim.operations.waveform_generator import generate_waveforms
import logging
from napari.qt.threading import thread_worker, create_worker
from time import sleep

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
        self.data_line = None       # Lines for graph


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

        for i in range(1,len(self.tab_widget)):
            self.tab_widget.setTabEnabled(i,False)

        self.run_worker = self._run()
        self.run_worker.start()
        # sleep(5)
        # self.volumetric_image_worker = self._volumetric_image()
        # self.volumetric_image_worker.yielded.connect(self.update_layer)
        # self.volumetric_image_worker.start()

    @thread_worker
    def _run(self):
        self.instrument.run(overwrite=self.volumetric_image['overwrite'].isChecked())
        self.end_scan()

    @thread_worker
    def _volumetric_image(self):

        while True:
            sleep(1/16)
            if type(self.instrument.im) == np.ndarray:
                im = self.instrument.im if not self.simulated else np.random.rand(self.cfg.sensor_row_count,
                                                                                  self.cfg.sensor_column_count)
                yield im

    def update_layer(self, im):

        """Update viewer with the newest image from scan"""

        try:
            key = 'Volumeteric Run'
            layer = self.viewer.layers[key]
            layer._slice.image._view = im
            layer.events.set_data()

        except KeyError:
            self.viewer.layers.clear()
            self.viewer.add_image(im, name='Volumeteric Run')

    def end_scan(self):

        self.instrument.livestream_enabled.clear()
        self.run_worker.quit()
        self.volumetric_image_worker.quit()

    def overwrite_warning(self):
        msgBox = QMessageBox()
        msgBox.setIcon(QMessageBox.Information)
        msgBox.setText("Running Acquisition will overwrite files. Are you sure you want to do this?")
        msgBox.setWindowTitle("Overwrite Files")
        msgBox.setStandardButtons(QMessageBox.Ok | QMessageBox.Cancel)
        return msgBox.exec()

    def waveform_graph(self):

        """Generate a graph of waveform for sanity check"""
        # TODO: change colors and make it a different pop up window. As of now it will interfere with widget placement
        self.waveform['generate'] = QPushButton('Generate Waveforms')
        self.colors = np.random.randint(0, 255,
                                        [12, 3])  # rework this so the colors are set and laser colors are consistent
        self.waveform['graph'] = PlotWidget()
        self.waveform['generate'].clicked.connect(self.waveform_update)

        return self.waveform['generate']

    def waveform_update(self):
        t, voltages_t = generate_waveforms(self.cfg, 488) #TODO: Rework so it's using active laser

        self.waveform['graph'].clear()
        for index, ao_name in enumerate(self.cfg.daq_ao_names_to_channels.keys()):
            self.waveform['graph'].addLegend(offset=(365, .5), horSpacing=20, verSpacing=0, labelTextSize='8pt')
            self.waveform['graph'].plot(t, voltages_t[index], name=ao_name,
                                        pen=mkPen(color=self.colors[index], width=3))
        try:
            self.viewer.window.remove_dock_widget(self.waveform['graph'])
        except LookupError:
            pass
        finally:
            self.viewer.window.add_dock_widget(self.waveform['graph'])






