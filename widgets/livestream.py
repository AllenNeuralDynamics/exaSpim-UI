from widgets.widget_base import WidgetBase
from qtpy.QtWidgets import QPushButton, QComboBox, QSpinBox, QLineEdit, QTabWidget, QListWidget, QListWidgetItem, QAbstractItemView, QMessageBox, QLabel,\
    QSlider, QCheckBox
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
        self.live_view_checks = {}
        self.waveform = {}
        self.selected = {}
        self.grid = {}
        self.pos_widget = {}
        self.pos_widget = {}  # Holds widgets related to sample position
        self.set_volume = {}  # Holds widgets related to setting volume limits during scan
        self.move_stage = {}
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

            try:        # TODO: This is hack for when tigerbox reply is split e.g. '3\r:A4 -76 0 \n'

                self.stage_position = self.instrument.sample_pose.get_position()
                # Update stage labels if stage has moved
                for direction in directions:
                    self.pos_widget[direction].setValue(int(self.stage_position[direction] * 1 / 10))
            except:
                pass


    def liveview_widget(self):

        """Contains button to activate livestream as well as selection of laser, autocontrast and rotation of
        liveview """

        self.live_view['start'] = QPushButton('Start Live View')
        self.live_view['start'].clicked.connect(self.start_live_view)

        self.live_view['edges'] = QPushButton("View Middle Edges")
        self.live_view['edges'].setCheckable(True)
        self.live_view['edges'].released.connect(self.enable_middle_edges)

        wv_strs = [str(x) for x in self.possible_wavelengths]
        self.live_view['wavelength'] = QListWidget()
        self.live_view['wavelength'].setSelectionMode(QAbstractItemView.MultiSelection)

        wv_item = {}
        for wavelength in wv_strs:
            wv_item[wavelength] = QListWidgetItem(wavelength)

            wv_item[wavelength].setBackground(QtGui.QColor(65, 72, 81, 255))
            self.live_view['wavelength'].addItem(wv_item[wavelength])
        self.live_view['wavelength'].itemPressed.connect(self.color_change_list)

        self.live_view['wavelength'].setMaximumHeight(70)

        self.live_view_checks['scouting'] = QCheckBox('Scout Mode')
        self.live_view_checks['crosshairs'] = QCheckBox('Crosshairs')
        self.live_view_checks['crosshairs'].stateChanged.connect(self.show_crosshairs)

        self.live_view['checkboxes'] = self.create_layout(struct='H', **self.live_view_checks)

        return self.create_layout(struct='VH', **self.live_view)

    def show_crosshairs(self, state):

        """Create or remove crosshair layer"""

        # State is 2 if checkmark is pressed
        if state == 2:

            vert_line = np.array([[0, self.cfg.tile_size_x_um * .5], [self.cfg.tile_size_y_um, self.cfg.tile_size_x_um * .5]])
            horz_line = np.array([[self.cfg.tile_size_y_um * .5, 0], [self.cfg.tile_size_y_um * .5, self.cfg.tile_size_x_um]])
            l = [vert_line, horz_line]
            color = ['blue', 'green']

            shapes_layer = self.viewer.add_shapes(l, shape_type='line', edge_width=30, edge_color=color, name='Crosshair')
            shapes_layer.mode = 'select'

        # State is 0 if checkmark is unpressed
        if state == 0:
            try:
                self.viewer.layers.remove('Crosshair')
            except ValueError:
                pass

    def start_live_view(self):

        """Start livestreaming"""

        self.disable_button(self.live_view['start'])

        wavelengths = [int(item.text()) for item in self.live_view['wavelength'].selectedItems()]
        wavelengths.sort()
        
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

        self.instrument.start_livestream(wavelengths, self.live_view_checks['scouting'].isChecked())
        self.livestream_worker = create_worker(self.instrument._livestream_worker)
        self.livestream_worker.finished.connect(self.stop_livestream)
        if self.live_view['edges'].isChecked():
            self.livestream_worker.yielded.connect(self.dissect_image)
        else:
            self.livestream_worker.yielded.connect(self.update_layer)
        self.livestream_worker.start()

        self.sample_pos_worker = self._sample_pos_worker()
        self.sample_pos_worker.start()



        self.live_view['start'].clicked.connect(self.stop_live_view)
        # Only allow stopping once everything is initialized
        # to avoid crashing gui

    def stop_livestream(self):

        """Call stop livestream only after livestream thread has finished.
        If camera is stopped before livestream thread, stalling can occur"""

        self.instrument.stop_livestream()

    def stop_live_view(self):

        """Stop livestreaming"""
        self.livestream_worker.quit()
        self.sample_pos_worker.quit()
        self.disable_button(self.live_view['start'])
        self.live_view['start'].clicked.disconnect(self.stop_live_view)
        self.live_view['start'].setText('Start Live View')
        self.live_view['start'].clicked.connect(self.start_live_view)
        self.live_view_checks['crosshairs'].setChecked(False)

    def disable_button(self, button, pause=3000):

        """Function to disable button clicks for a period of time to avoid crashing gui"""

        button.setEnabled(False)
        QtCore.QTimer.singleShot(pause, lambda: button.setDisabled(False))

    def enable_middle_edges(self):

        """Function to just show 1024x1024 of top, bottom, left, right of image"""

        if not self.instrument.livestream_enabled.is_set():
            return
        self.live_view_checks['crosshairs'].setChecked(False)
        self.viewer.layers.clear()
        if self.live_view['edges'].isChecked():
            self.livestream_worker.yielded.connect(self.dissect_image)
            self.livestream_worker.yielded.disconnect(self.update_layer)
        else:
            self.livestream_worker.yielded.disconnect(self.dissect_image)
            self.livestream_worker.yielded.connect(self.update_layer)


    def dissect_image(self, args):

        """Dissecting edges of image and displaying them in viewer"""

        try:
            (image, layer_num) = args

            chunk = 1024

            lower_col = round((self.cfg.column_count_px/2)-chunk)
            upper_col = round((self.cfg.column_count_px/2)+chunk)
            lower_row = round((self.cfg.row_count_px / 2) - chunk)
            upper_row = round((self.cfg.row_count_px / 2) + chunk)

            len = chunk*2
            width = chunk*4

            container = np.zeros((len, width))
            container[:chunk, chunk:chunk+len] = image[0][:chunk, lower_col:upper_col] # Top
            container[-chunk:, chunk:chunk+len] = image[0][-chunk:,lower_col:upper_col]  # bottom
            container[:, :chunk] = image[0][lower_row:upper_row, :chunk]  # left
            container[:, -chunk:] = image[0][lower_row:upper_row,-chunk:]  # right

            layer = self.viewer.layers[f"Video {layer_num} Edges"]
            layer.data = container

        except KeyError:
            # Add image to a new layer if layer doesn't exist yet
            self.viewer.add_image(container, name=f"Video {layer_num} Edges")
        except TypeError:
            pass



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

    def color_change_list(self, item):

        """Changes selected items color in Qlistwidget"""

        wl = item.text()
        if item.isSelected():
            item.setBackground(QtGui.QColor(self.cfg.channel_specs[wl]['color']))
        else:
            item.setBackground(QtGui.QColor(65, 72, 81, 255))   # Napari widget default color

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
        sleep(2)
        self.log.info('Starting stage update')
        # While livestreaming and looking at the first tab the stage position updates
        while self.instrument.livestream_enabled.is_set():
            if self.tab_widget.currentIndex() == 0:
                moved = False
                try:
                    self.sample_pos = self.instrument.sample_pose.get_position()
                    for direction in self.sample_pos.keys():
                        if direction in self.pos_widget.keys():
                            new_pos = int(self.sample_pos[direction] * 1 / 10)
                            if self.pos_widget[direction].value() != new_pos:
                                self.pos_widget[direction].setValue(new_pos)
                                moved = True

                    if self.instrument.scout_mode and moved:
                        self.start_stop_ni()
                    self.update_slider(self.sample_pos)  # Update slide with newest z depth
                except:
                    # Deal with garbled replies from tigerbox
                    pass

            yield


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

    def move_stage_widget(self):

        """Widget to move stage up and down w/o joystick control"""

        z_position = self.instrument.tigerbox.get_position('z')
        self.z_limit = self.instrument.sample_pose.get_travel_limits('y')
        self.z_limit['y'] = [round(x*1000) for x in self.z_limit['y']]
        self.z_range = self.z_limit["y"][1] + abs(self.z_limit["y"][0]) # Shift range up by lower limit so no negative numbers
        self.move_stage['up'] = QLabel(
            f'Upper Limit: {round(self.z_limit["y"][0])}')  # Upper limit will be the more negative limit
        self.move_stage['slider'] = QSlider()
        self.move_stage['slider'].setOrientation(QtCore.Qt.Vertical)
        self.move_stage['slider'].setInvertedAppearance(True)
        self.move_stage['slider'].setMinimum(self.z_limit["y"][0])
        self.move_stage['slider'].setMaximum(self.z_limit["y"][1])
        self.move_stage['slider'].setValue(int(z_position['Z']/10))
        self.move_stage['slider'].setTracking(False)
        self.move_stage['slider'].sliderReleased.connect(self.move_stage_vertical_released)
        self.move_stage['low'] = QLabel(
            f'Lower Limit: {round(self.z_limit["y"][1])}')  # Lower limit will be the more positive limit

        self.move_stage['halt'] = QPushButton('HALT')
        self.move_stage['halt'].clicked.connect(self.update_slider)
        self.move_stage['halt'].clicked.connect(lambda pressed=True, button=self.move_stage['halt']:
                                                self.disable_button(pressed,button))
        self.move_stage['halt'].clicked.connect(self.instrument.tigerbox.halt)

        self.move_stage['position'] = QLineEdit(str(z_position['Z']))
        self.move_stage['position'].setValidator(QtGui.QIntValidator(self.z_limit["y"][0],self.z_limit["y"][1]))
        self.move_stage['slider'].sliderMoved.connect(self.move_stage_textbox)
        self.move_stage_textbox(int(z_position['Z']))
        self.move_stage['position'].returnPressed.connect(self.move_stage_vertical_released)



        return self.create_layout(struct='V', **self.move_stage)

    def move_stage_vertical_released(self, location=None):

        """Move stage to location and stall until stopped"""

        if location==None:
            location = int(self.move_stage['position'].text())
            self.move_stage['slider'].setValue(location)
            self.move_stage_textbox(location)
        self.tab_widget.setTabEnabled(len(self.tab_widget)-1, False)
        self.move_stage_worker = create_worker(lambda location = location*10: self.instrument.tigerbox.move_absolute(z=location))
        self.move_stage_worker.start()
        self.move_stage_worker.finished.connect(lambda:self.enable_stage_slider())

    def enable_stage_slider(self):

        """Enable stage slider after stage has finished moving"""
        self.move_stage['slider'].setEnabled(True)
        self.move_stage['position'].setEnabled(True)
        self.tab_widget.setTabEnabled(len(self.tab_widget) - 1, True)


    def move_stage_textbox(self, location):

        position = self.move_stage['slider'].pos()
        self.move_stage['position'].setText(str(location))
        self.move_stage['position'].move(QtCore.QPoint(position.x() + 30,
                                                      round(position.y() + (-5)+((location+ abs(self.z_limit["y"][0]))/
                                                      self.z_range*(self.move_stage['slider'].height()-10)))))

    def update_slider(self, location:dict):

        """Update position of slider if stage halted. Location will be sample pose"""

        if type(location) == bool:      # if location is bool, then halt button was pressed
            self.move_stage_worker.quit()
            location = self.instrument.tigerbox.get_position('z')
        self.move_stage_textbox(int(location['y']/10))
        self.move_stage['slider'].setValue(int(location['y']/10))
