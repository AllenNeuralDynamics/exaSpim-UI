import logging
from widgets.widget_base import WidgetBase
from qtpy.QtWidgets import QPushButton, QTabWidget, QWidget, QLineEdit, QComboBox, QMessageBox, QCheckBox
import pyqtgraph.opengl as gl
import numpy as np
from napari.qt.threading import thread_worker,create_worker
from time import sleep
from pyqtgraph.Qt import QtCore, QtGui
import qtpy.QtGui
import stl
import pyqtgraph as pg
import tifffile
import blend_modes


class TissueMap(WidgetBase):

    def __init__(self, instrument, viewer):

        self.x_axis = None
        self.y_axis = None
        self.z_axis = None
        self.instrument = instrument
        self.viewer = viewer
        self.cfg = self.instrument.cfg
        self.log = logging.getLogger(__name__ + "." + self.__class__.__name__)
        self.tab_widget = None
        self.map_pos_worker = None
        self.camera_fov = None
        self.plot = None
        self.map_pos_alive = False

        self.rotate = {}
        self.map = {}
        self.origin = {}
        self.overview = {}
        self.initial_volume = [self.cfg.volume_x_um, self.cfg.volume_y_um, self.cfg.volume_z_um]
        self.sample_pose_remap = self.cfg.sample_pose_kwds['axis_map']
        self.og_axis_remap = {v: k for k, v in self.sample_pose_remap.items()}
        self.tiles = []  # Tile in sample pose coords
        self.grid_step_um = {}  # Grid steps in samplepose coords
        self.gl_overview = None
        self.tile_offset = self.remap_axis({'x': (.5 * 0.001 * (self.cfg.tile_specs['x_field_of_view_um'])),
                                            'y': (.5 * 0.001 * (self.cfg.tile_specs['y_field_of_view_um'])),
                                            'z': 0})
        self.gl_overview_pos = []
        self.gl_overview = []

    def set_tab_widget(self, tab_widget: QTabWidget):

        """Set the tabwidget that contains main, wavelength, and tissue map tab"""

        self.tab_widget = tab_widget
        self.tab_widget.tabBarClicked.connect(self.stage_positon_map)   # When tab bar is clicked see what tab its on

    def stage_positon_map(self, index):

        """Check if tab clicked is tissue map tab and start stage update when on tissue map tab
        :param index: clicked tab index. Tissue map is last tab"""

        last_index = len(self.tab_widget) - 1
        if index == last_index:                 # Start stage update when on tissue map tab
            self.map_pos_worker = self._map_pos_worker()
            self.map_pos_alive = True
            self.map_pos_worker.finished.connect(self.map_pos_worker_finished)
            self.map_pos_worker.start()

        else:                                   # Quit updating tissue map if not on tissue map tab
            if self.map_pos_worker is not None:
                self.map_pos_worker.quit()

            pass

    def map_pos_worker_finished(self):
        """Sets map_pos_alive to false when worker finishes"""
        print('map_pos_worker_finished')
        self.map_pos_alive = False

    def overview_widget(self):

        """Widgets for setting up a quick scan"""

        self.overview['start'] = QPushButton('Start overview')
        self.overview['start'].pressed.connect(self.start_overview)

        return self.create_layout(struct='V', **self.overview)

    def start_overview(self):

        """Start overview function of instrument"""
        self.overview['start'].blockSignals(True)  # Block release signal so progress bar doesn't start
        if self.instrument.livestream_enabled.is_set():
            self.error_msg('Livestreaming',
                           'Please stop the livestream before starting overview.')
            self.overview['start'].blockSignals(False)
            return

        if len(self.cfg.imaging_specs["laser_wavelengths"]) > 1:
            self.error_msg('One Channel',
                           'Please select only one channel for overview')
            self.overview['start'].blockSignals(False)
            return

        return_value = self.scan_summary()
        if return_value == QMessageBox.Cancel:
            self.overview['start'].blockSignals(False)
            return
        self.overview['start'].blockSignals(False)
        self.overview['start'].released.emit()  # Start progress bar

        self.map_pos_worker.quit()  # Stopping tissue map update
        for i in range(0, len(self.tab_widget)): self.tab_widget.setTabEnabled(i, False)  # Disable tabs during scan

        self.overview_worker = self._overview_worker()
        self.overview_worker.finished.connect(lambda: self.overview_finish())  # Napari threads have finished signals
        self.overview_worker.start()

        self.viewer.layers.clear()  # Clear existing layers
        self.volumetric_image_worker = create_worker(self.instrument._livestream_worker)
        self.volumetric_image_worker.yielded.connect(self.update_layer)
        self.volumetric_image_worker.start()

    def overview_finish(self):

        """Function to be executed at the end of the overview"""

        self.volumetric_image_worker.quit()

        for i in range(0, len(self.tab_widget)): self.tab_widget.setTabEnabled(i, True)  # Enabled tabs

        x_overlap_um = round((self.cfg.tile_overlap_x_percent / 100) * self.cfg.tile_specs['x_field_of_view_um'])
        y_overlap_um = round((self.cfg.tile_overlap_y_percent / 100) * self.cfg.tile_specs['y_field_of_view_um'])
        self.scale_x = (
                (((self.cfg.tile_specs['x_field_of_view_um'] * self.xtiles) - (x_overlap_um * (self.xtiles - 1))) * 0.001)
                / self.overview_array[0].shape[1])

        self.scale_y = (
                (((self.cfg.tile_specs['y_field_of_view_um'] * self.ytiles) - (y_overlap_um * (self.ytiles - 1))) * 0.001)
                / self.overview_array[0].shape[0])

        j = 0
        colormap_array = [None] * len(self.cfg.channels)
        for wl, image in zip(self.cfg.channels, self.overview_array):
            key = f'Overview {wl}'
            self.viewer.add_image(image, name=key,
                                  scale=[self.scale_x * 1000,
                                         self.scale_y * 1000])  # scale so it won't be squished in viewer
            self.viewer.layers[key].blending = 'additive'

            wl_color = self.cfg.channel_specs[str(wl)]['color']
            rgb = [x / 255 for x in qtpy.QtGui.QColor(wl_color).getRgb()]

            max = np.percentile(image, 90)
            min = np.percentile(image, 5)
            image.clip(min, max, out=image)
            image -= min
            image = np.floor_divide(np.flip(image), (max - min) / 256, out=image, casting='unsafe')
            overview_RGBA = \
                pg.makeRGBA(image, levels=[0, 256])[0]  # GLImage needs to be RGBA
            for i in range(0, len(rgb)):
                overview_RGBA[:, :, i] = overview_RGBA[:, :, i] * rgb[i]
            colormap_array[j] = overview_RGBA
            j += 1
        blended = colormap_array[0]
        for i in range(1, len(colormap_array)):
            alpha = 1 - (i / (i + 1))
            blended = blend_modes.darken_only(blended.astype('f8'), colormap_array[i].astype('f8'), alpha)

        final_RGBA = pg.makeRGBA(blended, levels=[0, 256])[0]
        self.gl_overview.append(gl.GLImageItem(final_RGBA, glOptions='translucent'))
        gui_coord = self.remap_axis({k: v * 0.0001 for k, v in self.instrument.sample_pose.get_position().items()})
        self.gl_overview_pos.append({'x':gui_coord['x'] - self.tile_offset['x'],
                                    'y': gui_coord['y'] - self.tile_offset['y'],
                                    'z': gui_coord['z'] + (self.tile_offset['z']*(self.xtiles))})
        self.gl_overview[-1].setTransform(
                            qtpy.QtGui.QMatrix4x4(0.0, 0.0, 1.0, gui_coord['x'] - self.tile_offset['x'],
                                                  0.0, self.scale_y, 0.0, gui_coord['y'] - self.tile_offset['y'],
                                                  self.scale_x, 0.0, 0.0, gui_coord['z'] - (self.tile_offset['z']),
                                                  0.0, 0.0, 0.0, 1.0))

        self.plot.removeItem(self.setup)
        self.plot.addItem(self.gl_overview[-1])  # GlImage doesn't like threads, do this outside of thread
        self.plot.addItem(self.setup)  # Remove and add objectives to see view through them

        self.map_pos_worker = self._map_pos_worker()
        self.map_pos_alive = True
        self.map_pos_worker.finished.connect(self.map_pos_worker_finished)
        self.map_pos_worker.start()  # Restart map update

    @thread_worker
    def _overview_worker(self):

        self.x_grid_step_um, self.y_grid_step_um = self.instrument.get_xy_grid_step(self.cfg.tile_overlap_x_percent,
                                                                                    self.cfg.tile_overlap_y_percent)

        while self.map_pos_alive == True:   # Stalling til map pos worker quits
            sleep(.5)
            yield
        self.overview_array, self.xtiles, self.ytiles = self.instrument.overview_scan()


        # self.overview_array = [tifffile.imread(fr'D:\overview_img_488_2023-08-07_09-09-36.tiff')]
        # self.xtiles = 4
        # self.ytiles = 3

        # Recalculate Limits based on new zero in place
        limits = self.remap_axis({'x': [-27, 9], 'y': [-7, 7], 'z': [-3, 20]}) if self.instrument.simulated else \
            self.remap_axis(self.instrument.sample_pose.get_travel_limits(*['x', 'y', 'z']))
        low = {}
        up = {}
        axes_len = {}
        for dir in limits:
            low[dir] = limits[dir][0] if limits[dir][0] < limits[dir][1] else limits[dir][1]
            up[dir] = limits[dir][1] if limits[dir][1] > limits[dir][0] else limits[dir][0]
            axes_len[dir] = abs(round(up[dir] - low[dir]))
            self.origin[dir] = round(low[dir] + (axes_len[dir] / 2))

        self.x_axis.setSize(*(axes_len['z'], axes_len['y']))
        self.x_axis.translate(*(low['x'], self.origin['y'], self.origin['z']))  # Translate to lower end of x and origin of y and -z
        self.x_axis.setTransform(
                            qtpy.QtGui.QMatrix4x4(0.0, 0.0, 1.0, low['x'],
                                                  0.0, 1, 0.0, self.origin['y'],
                                                  1, 0.0, 0.0, self.origin['z'],
                                                  0.0, 0.0, 1.0, 0.0))
        #     = self.create_axes((90, 0, 1, 0),
        #                                (axes_len['z'], axes_len['y']),
        #                                (low['x'], self.origin['y'], self.origin['z']))
        #
        # # y axes: Translate to lower end of y and origin of x and -z
        # self.y_axis = self.create_axes((90, 1, 0, 0),
        #                                (axes_len['x'], axes_len['z']),
        #                                (self.origin['x'], low['y'], self.origin['z']))
        #
        # # z axes: Translate to origin of x, y, z
        # self.z_axis = self.create_axes((0, 0, 0, 0),
        #                                (axes_len['x'], axes_len['y']),
        #                                (self.origin['x'], self.origin['y'], low['z']))


    def scan_summary(self):

        x, y, z = self.instrument.get_tile_counts(self.cfg.tile_overlap_x_percent,
                                                           self.cfg.tile_overlap_y_percent,
                                                           8,
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
                       f"Saving as: {self.cfg.local_storage_dir}\overview_img_{'_'.join(map(str, self.cfg.channels))}\n"
                       f"Press cancel to abort run")
        msgBox.setWindowTitle("Scan Summary")
        msgBox.setStandardButtons(QMessageBox.Ok | QMessageBox.Cancel)
        return msgBox.exec()

    def mark_graph(self):

        """Mark graph with pertinent landmarks"""

        self.map['color'] = QComboBox()
        self.map['color'].addItems(qtpy.QtGui.QColor.colorNames())      # Add all QtGui Colors to drop down box

        self.map['mark'] = QPushButton('Set Point')
        self.map['mark'].clicked.connect(self.set_point)                # Add point when button is presses

        self.map['label'] = QLineEdit()
        self.map['label'].returnPressed.connect(self.set_point)         # Add text when button is pressed

        self.checkbox = {}

        self.checkbox['tiling'] = QCheckBox('See Tiling')
        self.checkbox['tiling'].stateChanged.connect(self.set_tiling)        # Display tiling of scan when checked

        self.map['checkboxes'] = self.create_layout(struct='H', **self.checkbox)

        return self.create_layout(struct='H', **self.map)

    def set_tiling(self, state):

        """Calculate grid steps and number of tiles for scan volume in config.
        :param state: state of QCheckbox when clicked. State 2 means checkmark is pressed: state 0 unpressed"""

        # State is 2 if checkmark is pressed
        if state == 2:
            #self.plot.setEnabled(False)
            # Grid steps in sample pose coords
            self.x_grid_step_um, self.y_grid_step_um = self.instrument.get_xy_grid_step(self.cfg.tile_overlap_x_percent,
                                                                                        self.cfg.tile_overlap_y_percent)
            # Tile in sample pose coords
            self.xtiles, self.ytiles, self.ztiles = self.instrument.get_tile_counts(self.cfg.tile_overlap_x_percent,
                                                                                    self.cfg.tile_overlap_y_percent,
                                                                                    self.cfg.z_step_size_um,
                                                                                    self.cfg.volume_x_um,
                                                                                    self.cfg.volume_y_um,
                                                                                    self.cfg.volume_z_um)

        # State is 0 if checkmark is unpressed
        if state == 0:
            #self.plot.setEnabled(True)
            for item in self.tiles:
                if item in self.plot.items:
                    self.plot.removeItem(item)

    def set_point(self):

        """Set current position as point on graph"""

        # Remap sample_pos to gui coords and convert 1/10um to mm
        gui_coord = self.remap_axis({k: v * 0.0001 for k, v in self.map_pose.items()})  # if not self.instrument.simulated \
                                    #     else np.random.randint(-60000, 60000, 3)
        gui_coord = [i for i in gui_coord.values()]  # Coords for point needs to be a list
        hue = str(self.map['color'].currentText())   # Color of point determined by drop down box
        point = gl.GLScatterPlotItem(pos=gui_coord, size=.35, color=qtpy.QtGui.QColor(hue), pxMode=False)
        info = self.map['label'].text() # Text comes from textbox
        text = info if info != '' else ", ".join(map(str, [round(x,2) for x in gui_coord]))
        info_point = gl.GLTextItem(pos=gui_coord, text=text, font=qtpy.QtGui.QFont('Helvetica', 10))
        self.plot.addItem(info_point)               # Add items to plot
        self.plot.addItem(point)

        self.map['label'].clear()                   # Clear text box

    @thread_worker
    def _map_pos_worker(self):

        """Update position of stage for tissue map, draw scanning volume, and tiling"""
        while True:

            try:    # TODO: This is hack for when tigerbox reply is split e.g. '3\r:A4 -76 0 \n'
                self.map_pose = self.instrument.sample_pose.get_position()
                # Convert 1/10um to mm
                coord = {k: v * 0.0001 for k, v in self.map_pose.items()}  #if not self.instrument.simulated \
                     #else np.random.randint(-60000, 60000, 3)

                gui_coord = self.remap_axis(coord)  # Remap sample_pos to gui coords
                self.stage_pos.setData(pos=[gui_coord['x'], gui_coord['y'], gui_coord['z']])
                self.camera_fov.setTransform(qtpy.QtGui.QMatrix4x4(1.0, 0.0, 0.0, gui_coord['x']- self.tile_offset['x'],
                                                              0.0, 1.0, 0.0, gui_coord['y'] - self.tile_offset['y'],
                                                              0.0, 0.0, 1.0, gui_coord['z'] - self.tile_offset['z'],
                                                              0.0, 0.0, 0.0, 1.0))

                self.setup.setTransform(
                    qtpy.QtGui.QMatrix4x4(0.0, 0.0, 1.0, gui_coord['x'],  # Translate mount up and down and side to side
                                          1.0, 0.0, 0.0, gui_coord['y'],
                                          0.0, 1.0, 0.0, gui_coord['z'],
                                          0.0, 0.0, 0.0, 1.0))


                if self.instrument.start_pos == None:

                    # Translate volume of scan to gui coordinate plane
                    scanning_volume = self.remap_axis({k: self.cfg.imaging_specs[f'volume_{k}_um'] * .001
                                                       for k in self.map_pose.keys()})
                    # Scan vol appears upward to show what section of mount will be scanned as the mount moves downward

                    self.scan_vol.setSize(**scanning_volume)
                    self.scan_vol.setTransform(qtpy.QtGui.QMatrix4x4(1, 0, 0, gui_coord['x'] - self.tile_offset['x'],
                                                                     0, 1, 0, gui_coord['y'] - self.tile_offset['y'],
                                                                     0, 0, 1, gui_coord['z'] - self.tile_offset['z'],
                                                                     0, 0, 0, 1))

                    if self.checkbox['tiling'].isChecked():
                        if old_coord != gui_coord or self.tiles == [] or \
                                self.initial_volume != [self.cfg.volume_x_um, self.cfg.volume_y_um, self.cfg.volume_z_um]:
                            self.draw_tiles(gui_coord)  # Draw tiles if checkbox is checked if something has changed

                else:

                    # Remap start position and shift position of scan vol to center of camera fov and convert um to mm
                    start = self.remap_axis({'x': self.instrument.start_pos['x'] - self.tile_offset['x'],
                                             'y': self.instrument.start_pos['y'] - self.tile_offset['y'],
                                             'z': self.instrument.start_pos['z']- self.tile_offset['z']})

                    if self.map['tiling'].isChecked():
                        self.draw_tiles(start)
                    self.draw_volume(start, self.remap_axis({k : self.cfg.imaging_specs[f'volume_{k}_um'] * .001
                                                       for k in self.map_pose.keys()}))
            except:
                pass
            finally:
                old_coord = gui_coord
                yield   # Yield so thread can stop


    def draw_tiles(self, coord):

        """Draw tiles of proposed scan volume.
        :param coord: coordinates of bottom corner of volume in sample pose"""

        #Check if volume in config has changed
        if self.initial_volume != [self.cfg.volume_x_um, self.cfg.volume_y_um, self.cfg.volume_z_um]:
            self.set_tiling(2)  # Update grid steps and tile numbers
            self.initial_volume = [self.cfg.volume_x_um, self.cfg.volume_y_um, self.cfg.volume_z_um]

        for item in self.tiles:
            if item in self.plot.items:
                self.plot.removeItem(item)

        self.tiles.clear()
        for x in range(0, self.xtiles):
            for y in range(0, self.ytiles):
                tile_offset = self.remap_axis({'x': (x * self.x_grid_step_um * .001)- (.5 * 0.001 * (self.cfg.tile_specs['x_field_of_view_um'])),
                                               'y': (y * self.y_grid_step_um * .001)- (.5 * 0.001 * (self.cfg.tile_specs['y_field_of_view_um'])),
                                               'z': 0})
                tile_pos = {
                    'x': tile_offset['x'] + coord['x'],
                    'y': tile_offset['y'] + coord['y'],
                    'z': tile_offset['z'] + coord['z']
                    }
                num_pos = [tile_pos['x'],
                           tile_pos['y'] + (.5 * 0.001 * (self.cfg.tile_specs['y_field_of_view_um'])),
                           tile_pos['z'] - (.5 * 0.001 * (self.cfg.tile_specs['x_field_of_view_um']))]

                tile_volume = self.remap_axis({'x': self.cfg.tile_specs['x_field_of_view_um'] * .001,
                                               'y': self.cfg.tile_specs['y_field_of_view_um'] * .001,
                                               'z': self.ztiles * self.cfg.z_step_size_um * .001})
                self.tiles.append(self.draw_volume(tile_pos, tile_volume))
                self.tiles[-1].setColor(qtpy.QtGui.QColor('cornflowerblue'))
                self.plot.addItem(self.tiles[-1])
                self.tiles.append(
                    gl.GLTextItem(pos=num_pos, text=str(((self.ytiles-1)-y)+(self.ytiles*x)), font=qtpy.QtGui.QFont('Helvetica', 15)))
                self.plot.addItem(self.tiles[-1])  # Can't draw text while moving graph

    def draw_volume(self, coord: dict, size: dict):

        """draw and translate boxes in map. Expecting gui coordinate system"""

        box = gl.GLBoxItem()  # Representing scan volume
        box.translate(coord['x'], coord['y'], coord['z'])
        box.setSize(**size)
        return box

    def rotate_buttons(self):

        self.rotate['x-y'] = QPushButton("X/Y Plane")
        self.rotate['x-y'].clicked.connect(lambda click=None,
                                                  center=QtGui.QVector3D(self.origin['x'], self.origin['y'], 0),
                                                  elevation=90,
                                                  azimuth=0:
                                           self.rotate_graph(click, center, elevation, azimuth))

        self.rotate['x-z'] = QPushButton("X/Z Plane")
        self.rotate['x-z'].clicked.connect(lambda click=None,
                                                  center=QtGui.QVector3D(self.origin['x'], 0, -self.origin['z']),
                                                  elevation=0,
                                                  azimuth=90:
                                           self.rotate_graph(click, center, elevation, azimuth))

        self.rotate['y-z'] = QPushButton("Y/Z Plane")
        self.rotate['y-z'].clicked.connect(lambda click=None,
                                                  center=QtGui.QVector3D(0, self.origin['y'], -self.origin['z']),
                                                  elevation=0,
                                                  azimuth=0:
                                           self.rotate_graph(click, center, elevation, azimuth))

        return self.create_layout(struct='V', **self.rotate)

    def create_axes(self, rotation, size, translate, color=None):

        axes = gl.GLGridItem()
        axes.rotate(*rotation)
        axes.setSize(*size)
        axes.translate(*translate)  # Translate to lower end of x and origin of y and -z
        if color is not None: axes.setColor(qtpy.QtGui.QColor(color))
        self.plot.addItem(axes)
        return axes

    def rotate_graph(self, click, center, elevation, azimuth):

        """Rotate graph to specific view"""

        self.plot.opts['center'] = center
        self.plot.opts['elevation'] = elevation
        self.plot.opts['azimuth'] = azimuth

    def remap_axis(self, coords: dict, remap : dict = {}):

        """Remaps sample pose coordinates to gui 3d map coordinates.
        Sample pose comes in dictionary with uppercase keys and gui uses lowercase"""

        remap = {'x': 'z', 'y': 'x', 'z': '-y'} if remap == {} else remap
        remap_coords = {}

        for k, v in remap.items():
            if v.lstrip('-') not in coords.keys():
                continue
            if '-' in v:
                v = v.lstrip('-')
                remap_coords[k] = [i * -1 for i in coords[v]] \
                    if type(coords[v]) is list else -coords[v]
            else:
                remap_coords[k] = [i for i in coords[v]] \
                    if type(coords[v]) is list else coords[v]

        return remap_coords

    def graph(self):

        self.plot = gl.GLViewWidget()
        self.plot.opts['distance'] = 40

        limits = self.remap_axis({'x': [-27, 9], 'y': [-7, 7], 'z': [-3, 20]}) if self.instrument.simulated else \
            self.remap_axis(self.instrument.sample_pose.get_travel_limits(*['x', 'y', 'z']))
        low = {}
        up = {}
        axes_len = {}
        for dir in limits:
            low[dir] = limits[dir][0] if limits[dir][0] < limits[dir][1] else limits[dir][1]
            up[dir] = limits[dir][1] if limits[dir][1] > limits[dir][0] else limits[dir][0]
            axes_len[dir] = abs(round(up[dir] - low[dir]))
            self.origin[dir] = round(low[dir] + (axes_len[dir] / 2))
        self.plot.opts['center'] = QtGui.QVector3D(self.origin['x'], self.origin['y'], self.origin['z'])
        # x axes: Translate axis so origin of graph translate to center of stage limits
        # Z coords increase as stage moves down so z origin and coords are negative
        self.x_axis = self.create_axes((90, 0, 1, 0),
                         (axes_len['z'], axes_len['y']),
                         (low['x'], self.origin['y'], self.origin['z']))

        # y axes: Translate to lower end of y and origin of x and -z
        self.y_axis = self.create_axes((90, 1, 0, 0),
                         (axes_len['x'], axes_len['z']),
                         (self.origin['x'], low['y'], self.origin['z']))

        # z axes: Translate to origin of x, y, z
        self.z_axis = self.create_axes((0, 0, 0, 0),
                         (axes_len['x'], axes_len['y']),
                         (self.origin['x'], self.origin['y'], low['z']))

        # Representing scan volume
        self.scan_vol = gl.GLBoxItem(color = qtpy.QtGui.QColor('gold'))
        self.scan_vol.translate(low['x']- (.5 * 0.001 * (self.cfg.tile_specs['x_field_of_view_um'])),
                                self.origin['y']- (.5 * 0.001 * (self.cfg.tile_specs['y_field_of_view_um'])),
                                self.origin['z'])
        scanning_volume = self.remap_axis({'x': self.cfg.imaging_specs[f'volume_x_um'] * 1 / 1000,
                                           'y': self.cfg.imaging_specs[f'volume_y_um'] * 1 / 1000,
                                           'z': self.cfg.imaging_specs[f'volume_z_um'] * 1 / 1000})
        self.scan_vol.setSize(**scanning_volume)
        self.plot.addItem(self.scan_vol)

        # Current fov of camera
        self.camera_fov = gl.GLBoxItem()
        self.camera_fov.setSize(**self.remap_axis({'x': 0.001 * self.cfg.tile_specs['x_field_of_view_um'],
                                            'y': 0.001 * self.cfg.tile_specs['y_field_of_view_um'],
                                            'z': 0}))
        self.camera_fov.setColor(qtpy.QtGui.QColor('red'))
        self.plot.addItem(self.camera_fov)

        # Current position of stage
        self.stage_pos = gl.GLScatterPlotItem()
        self.stage_pos.setData(color=qtpy.QtGui.QColor('red'))
        self.plot.addItem(self.stage_pos)

        try:
            setup = stl.mesh.Mesh.from_file(r'C:\Users\Administrator\Downloads\exa-spim-tissue-map.stl')
            points = setup.points.reshape(-1, 3)
            faces = np.arange(points.shape[0]).reshape(-1, 3)

            setup = gl.MeshData(vertexes=points, faces=faces)
            self.setup = gl.GLMeshItem(meshdata=setup, smooth=True, drawFaces=True, drawEdges=False, color=(0.5, 0.5, 0.5, 0.5),
                              shader='edgeHilight', glOptions = 'translucent')
            self.plot.addItem(self.setup)

        except FileNotFoundError:
            # Create self.objectives and self.stage objects but don't add them to graph
            self.setup = gl.GLBoxItem()

        return self.plot
