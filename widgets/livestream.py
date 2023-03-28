from widgets.widget_base import WidgetBase
from qtpy.QtWidgets import QPushButton, QComboBox, QSpinBox, QLineEdit, QTabWidget, QListWidget, QListWidgetItem, QAbstractItemView, QMessageBox
import qtpy.QtGui as QtGui
import qtpy.QtCore as QtCore
import numpy as np
from math import ceil
from skimage.io import imsave
from napari.qt.threading import thread_worker, create_worker
from time import sleep
import logging


class Livestream(WidgetBase):

    def __init__(self, viewer, cfg, instrument, simulated: bool):

        """
            :param viewer: napari viewer
            :param cfg: config object from instrument
            :param instrument: instrument bing used
            :param simulated: if instrument is in simulate mode
        """

        self.cfg = cfg
        self.possible_wavelengths = self.cfg.possible_channels
        self.viewer = viewer
        self.instrument = instrument
        self.simulated = simulated

        self.log = logging.getLogger(__name__ + "." + self.__class__.__name__)

        self.live_view = {}
        self.waveform = {}
        self.selected = {}
        self.grid = {}
        self.pos_widget = {}
        self.pos_widget = {}  # Holds widgets related to sample position
        self.set_volume = {}  # Holds widgets related to setting volume limits during scan
        self.stage_position = None
        self.tab_widget = None
        self.sample_pos_worker = None
        self.end_scan = None

        self.livestream_worker = None
        self.scale = [self.cfg.cfg['tile_specs']['x_field_of_view_um'] / self.cfg.sensor_column_count,
                      self.cfg.cfg['tile_specs']['y_field_of_view_um'] / self.cfg.sensor_row_count]

    def set_tab_widget(self, tab_widget: QTabWidget):

        self.tab_widget = tab_widget
        self.tab_widget.tabBarClicked.connect(self.update_positon)

    def update_positon(self, index):

        directions = ['x', 'y', 'z']
        if index == 0 and not self.instrument.livestream_enabled.is_set():

            self.stage_position = self.instrument.sample_pose.get_position()
            # Update stage labels if stage has moved
            for direction in directions:
                self.pos_widget[direction].setValue(int(self.stage_position[direction] * 1 / 10))


    def liveview_widget(self):

        """Contains button to activate livestream as well as selection of laser, autocontrast and rotation of
        liveview """

        self.live_view['start'] = QPushButton('Start Live View')
        self.live_view['start'].clicked.connect(self.start_live_view)
        wv_strs = [str(x) for x in self.possible_wavelengths]
        self.live_view['wavelength'] = QListWidget()
        self.live_view['wavelength'].setSelectionMode(QAbstractItemView.MultiSelection)

        for wavelength in wv_strs:
            wv_item = QListWidgetItem(wavelength)
            wv_item.setBackground(QtGui.QColor(self.cfg.channel_specs[wavelength]['color']))
            self.live_view['wavelength'].addItem(wv_item)

        self.live_view['wavelength'].setStyleSheet(" QListWidget:item:selected:active {background: white;"
                                                   "color: black;"
                                                   "border: 2px solid green;"
                                                   "foreground: red; }")

        self.live_view['wavelength'].setMaximumHeight(70)
        self.live_view['wavelength'].setSortingEnabled(True)

        return self.create_layout(struct='H', **self.live_view)


    def start_live_view(self):

        """Start livestreaming"""

        self.disable_button(self.live_view['start'])

        wavelengths = [int(item.text()) for item in self.live_view['wavelength'].selectedItems()]
        if wavelengths == []:
            msgBox = QMessageBox()
            msgBox.setIcon(QMessageBox.Information)
            msgBox.setText("Please select lasers for livestream viewing")
            msgBox.setWindowTitle("No lasers selected")
            msgBox.setStandardButtons(QMessageBox.Ok)
            return msgBox.exec()

        self.live_view['start'].clicked.disconnect(self.start_live_view)
        if self.live_view['start'].text() == 'Start Live View':
            self.live_view['start'].setText('Stop Live View')

        self.instrument.start_livestream(wavelengths)
        self.livestream_worker = create_worker(self.instrument._livestream_worker)
        self.livestream_worker.yielded.connect(self.update_layer)
        self.livestream_worker.start()

        sleep(2)    # Allow livestream to start

        if not self.simulated:
            self.sample_pos_worker = self._sample_pos_worker()
            self.sample_pos_worker.start()


        self.live_view['start'].clicked.connect(self.stop_live_view)
        # Only allow stopping once everything is initialized
        # to avoid crashing gui

    def stop_live_view(self):

        """Stop livestreaming"""

        self.disable_button(self.live_view['start'])
        self.live_view['start'].clicked.disconnect(self.stop_live_view)
        self.instrument.stop_livestream()
        self.livestream_worker.quit()
        self.live_view['start'].setText('Start Live View')
        if self.sample_pos_worker != None: self.sample_pos_worker.quit()

        self.live_view['start'].clicked.connect(self.start_live_view)

    def disable_button(self, button, pause=3000):

        """Function to disable button clicks for a period of time to avoid crashing gui"""

        button.setEnabled(False)
        QtCore.QTimer.singleShot(pause, lambda: button.setDisabled(False))

    def update_layer(self, args):

        """Update viewer with new multiscaled camera frame"""
        (image, layer_num) = args

        try:
            layer = self.viewer.layers[f"Video {layer_num}"]
            layer.data = image
        except:
            # Add image to a new layer if layer doesn't exist yet
            self.viewer.add_image(image, name = f"Video {layer_num}",
                                         multiscale=True,
                                         scale = self.scale)
            self.viewer.layers[f"Video {layer_num}"].blending = 'additive'

    def sample_stage_position(self):

        """Creates labels and boxs to indicate sample position"""

        directions = ['x', 'y', 'z']
        self.stage_position = self.instrument.sample_pose.get_position()

        # Create X, Y, Z labels and displays for where stage is
        for direction in directions:
            self.pos_widget[direction + 'label'], self.pos_widget[direction] = \
                self.create_widget(self.stage_position[direction]*1/10, QSpinBox, f'{direction} [um]:')
            self.pos_widget[direction].setReadOnly(True)

        # Sets start position of scan to current position of sample
        self.set_volume['set_start'] = QPushButton()
        self.set_volume['set_start'].setText('Set Scan Start')
        self.set_volume['set_start'].clicked.connect(self.set_start_position)

        self.set_volume['clear'] = QPushButton()
        self.set_volume['clear'].setText('Clear')
        self.set_volume['clear'].clicked.connect(self.clear_start_position)
        self.set_volume['clear'].setHidden(True)

        self.pos_widget['volume_widgets'] = self.create_layout(struct='V', **self.set_volume)

        return self.create_layout(struct='H', **self.pos_widget)

    def set_start_position(self):

        """Set the starting position of the scan"""

        current = self.sample_pos if self.instrument.livestream_enabled.is_set() \
            else self.instrument.sample_pose.get_position()
        set_start = self.instrument.start_pos

        if set_start is None:
            self.set_volume['clear'].setHidden(False)
            self.instrument.set_scan_start(current)

    def clear_start_position(self):

        """Reset start position of scan to None which means the scan will start at current positon"""

        self.instrument.set_scan_start(None)

    @thread_worker
    def _sample_pos_worker(self):
        """Update position widgets for volumetric imaging or manually moving"""

        self.log.info('Starting stage update')
        # While livestreaming and looking at the first tab the stage position updates
        while True:

                while self.instrument.livestream_enabled.is_set() and self.tab_widget.currentIndex() == 0:

                    try:
                        self.sample_pos = self.instrument.sample_pose.get_position()
                        for direction, value in self.sample_pos.items():
                            if direction in self.pos_widget:
                                self.pos_widget[direction].setValue(int(value*1/10))  #Units in microns
                    except:
                        pass

                yield       # yield so thread can quit
                sleep(1)


    def screenshot_button(self):

        """Button that will take a screenshot of liveviewer"""
        # TODO: Add a way to specify where you want png to be saved

        screenshot_b = QPushButton()
        screenshot_b.setText('Screenshot')
        screenshot_b.clicked.connect(self.take_screenshot)
        return screenshot_b

    def take_screenshot(self):

        if self.viewer.layers != []:
            screenshot = self.viewer.screenshot()
            self.viewer.add_image(screenshot)
            imsave('screenshot.png', screenshot)
        else:
            self.error_msg('Screenshot', 'No image to screenshot')
