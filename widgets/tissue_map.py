import logging
from widgets.widget_base import WidgetBase
from qtpy.QtWidgets import QPushButton, QTabWidget, QWidget, QLineEdit, QComboBox, QMessageBox, QCheckBox
import pyqtgraph.opengl as gl
import numpy as np
from napari.qt.threading import thread_worker
from time import sleep
from pyqtgraph.Qt import QtCore, QtGui
import qtpy.QtGui


class TissueMap(WidgetBase):

    def __init__(self, instrument):

        self.instrument = instrument
        self.cfg = self.instrument.cfg
        self.log = logging.getLogger(__name__ + "." + self.__class__.__name__)
        self.tab_widget = None
        self.map_pos_worker = None
        self.pos = None
        self.plot = None

        self.rotate = {}
        self.map = {}
        self.origin = {}

        self.initial_volume = [self.cfg.volume_x_um, self.cfg.volume_y_um, self.cfg.volume_z_um]
        self.sample_pose_remap = self.cfg.sample_pose_kwds['axis_map']
        self.og_axis_remap = {v: k for k, v in self.sample_pose_remap.items()}
        self.tiles = {}  # Tile in sample pose coords
        self.grid_step_um = {}  # Grid steps in samplepose coords

    def set_tab_widget(self, tab_widget: QTabWidget):

        self.tab_widget = tab_widget
        self.tab_widget.tabBarClicked.connect(self.stage_positon_map)

    def stage_positon_map(self, index):
        last_index = len(self.tab_widget) - 1
        if index == last_index:
            self.map_pos_worker = self._map_pos_worker()
            self.map_pos_worker.start()

        else:
            if self.map_pos_worker is not None:
                self.map_pos_worker.quit()

            pass

    def mark_graph(self):

        """Mark graph with pertinent landmarks"""

        self.map['color'] = QComboBox()
        self.map['color'].addItems(qtpy.QtGui.QColor.colorNames())

        self.map['mark'] = QPushButton('Set Point')
        self.map['mark'].clicked.connect(self.set_point)

        self.map['label'] = QLineEdit()
        self.map['label'].returnPressed.connect(self.set_point)

        self.map['tiling'] = QCheckBox('See Tiling')
        self.map['tiling'].stateChanged.connect(self.set_tiling)

        return self.create_layout(struct='H', **self.map)

    def set_tiling(self, state):

        # State is 2 if checkmark is pressed
        if state == 2:
            # Grid steps in samplepose coords
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
            for item in self.plot.items:
                if type(item) == gl.GLBoxItem and item != self.scan_vol:
                    self.plot.removeItem(item)

    def set_point(self):

        """Set current position as point on graph"""

        gui_coord = self.remap_axis({'x': self.map_pose['x'] * 0.0001,
                                     'y': self.map_pose['y'] * 0.0001,
                                     'z': self.map_pose['z'] * 0.0001})  # if not self.instrument.simulated \
                                    #     else np.random.randint(-60000, 60000, 3)
        gui_coord = [i for i in gui_coord.values()]  # Coords for point needs to be a list
        hue = str(self.map['color'].currentText())
        point = gl.GLScatterPlotItem(pos=gui_coord, size=.35, color=qtpy.QtGui.QColor(hue), pxMode=False)
        info = self.map['label'].text()
        info_point = gl.GLTextItem(pos=gui_coord, text=info, font=qtpy.QtGui.QFont('Helvetica', 10))
        self.plot.addItem(info_point)
        self.plot.addItem(point)

        self.map['label'].clear()

    @thread_worker
    def _map_pos_worker(self):

        """Update position of stage for tissue map, draw scanning volume, and tiling"""

        while True:

            try:
                self.map_pose = self.instrument.sample_pose.get_position()
                # Convert 1/10um to mm
                coord = {'x': self.map_pose['x'] * 0.0001,
                         'y': self.map_pose['y'] * 0.0001,
                         'z': self.map_pose['z'] * 0.0001}  # if not self.instrument.simulated \
                #     else np.random.randint(-60000, 60000, 3)

                gui_coord = self.remap_axis(coord)  # Remap sample_pos to gui coords
                self.pos.setData(pos=[gui_coord['x'], gui_coord['y'], gui_coord['z']])  # Set position as list

                if self.instrument.start_pos == None:
                    for item in self.plot.items:        # Remove previous scan vol and tiles
                        if type(item) == gl.GLBoxItem:
                            self.plot.removeItem(item)

                    # Shift position of scan vol to center of camera fov and convert um to mm
                    volume_pos = {'x': coord['x'] - (.5 * 0.001 * (self.cfg.tile_specs['x_field_of_view_um'])),
                                  'y': coord['y'] - (.5 * 0.001 * (self.cfg.tile_specs['y_field_of_view_um'])),
                                  'z': coord['z']}
                    # Translate volume of scan to gui coordinate plane
                    scanning_volume = self.remap_axis({'x': self.cfg.imaging_specs[f'volume_x_um'] * 1 / 1000,
                                                       'y': self.cfg.imaging_specs[f'volume_y_um'] * 1 / 1000,
                                                       'z': self.cfg.imaging_specs[f'volume_z_um'] * 1 / 1000})

                    self.scan_vol = self.draw_volume(self.remap_axis(volume_pos), scanning_volume)  # Draw volume
                    self.plot.addItem(self.scan_vol)    # Add volume to graph

                    if self.map['tiling'].isChecked():
                        self.draw_tiles(volume_pos) # Draw tiles if checkbox is checked

                else:

                    # Remap start position and shift position of scan vol to center of camera fov and convert um to mm
                    start = self.remap_axis({'x': self.instrument.start_pos['x'] - (.5 * 0.001 * (self.cfg.tile_specs['x_field_of_view_um'])),
                                             'y': self.instrument.start_pos['y'] - (.5 * 0.001 * (self.cfg.tile_specs['y_field_of_view_um'])),
                                             'z': self.instrument.start_pos['z']})

                    if self.map['tiling'].isChecked():
                        self.draw_tiles(start)
                    self.draw_volume(start, self.remap_axis({'x': self.cfg.imaging_specs[f'volume_x_um'] * 1 / 1000,
                                                             'y': self.cfg.imaging_specs[f'volume_y_um'] * 1 / 1000,
                                                             'z': self.cfg.imaging_specs[f'volume_z_um'] * 1 / 1000}))
            except:
                # In case Tigerbox throws an error
                sleep(2)
            finally:
                sleep(.5)
                yield   # Yeild so thread can stop

    def draw_tiles(self, coord):

        """Draw tiles of proposed scan volume.
        :param coord: coordinates of bottom corner of volume in sample pose"""

        if self.initial_volume != [self.cfg.volume_x_um, self.cfg.volume_y_um, self.cfg.volume_z_um]:
            self.set_tiling(2)
            self.initial_volume = [self.cfg.volume_x_um, self.cfg.volume_y_um, self.cfg.volume_z_um]

        for item in self.plot.items:
            if type(item) == gl.GLBoxItem and item != self.scan_vol:
                self.plot.removeItem(item)

        for x in range(0, self.xtiles):
            for y in range(0, self.ytiles):
                tile_pos = self.remap_axis({'x': round(x * self.x_grid_step_um * .001) + coord['x'],
                                            'y': round(y * self.y_grid_step_um * .001) + coord['y'],
                                            'z': coord['z']})

                tile_volume = self.remap_axis({'x': self.cfg.tile_specs['x_field_of_view_um'] * .001,
                                               'y': self.cfg.tile_specs['y_field_of_view_um'] * .001,
                                               'z': 0})
                tile = self.draw_volume(tile_pos, tile_volume)
                tile.setColor(qtpy.QtGui.QColor('cornflowerblue'))
                self.plot.addItem(tile)

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

    def rotate_graph(self, click, center, elevation, azimuth):

        """Rotate graph to specific view"""

        self.plot.opts['center'] = center
        self.plot.opts['elevation'] = elevation
        self.plot.opts['azimuth'] = azimuth

    def remap_axis(self, coords: dict):

        """Remaps sample pose coordinates to gui 3d map coordinates.
        Sample pose comes in dictionary with uppercase keys and gui uses lowercase"""

        remap = {'x': 'z', 'y': 'x', 'z': '-y'}
        remap_coords = {}

        for k, v in remap.items():
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

        limits = self.remap_axis({'x': [0, 45], 'y': [0, 60], 'z': [0, 55]}) if self.instrument.simulated else \
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
        self.create_axes((90, 0, 1, 0),
                         (axes_len['z'], axes_len['y']),
                         (low['x'], self.origin['y'], self.origin['z']))

        # y axes: Translate to lower end of y and origin of x and -z
        self.create_axes((90, 1, 0, 0),
                         (axes_len['x'], axes_len['z']),
                         (self.origin['x'], low['y'], self.origin['z']))

        # z axes: Translate to origin of x, y, z
        self.create_axes((0, 0, 0, 0),
                         (axes_len['x'], axes_len['y']),
                         (self.origin['x'], self.origin['y'], low['z']))

        # Representing scan volume
        self.scan_vol = gl.GLBoxItem()
        self.scan_vol.translate(self.origin['x'], self.origin['y'], up['z'])
        scanning_volume = self.remap_axis({'x': self.cfg.imaging_specs[f'volume_x_um'] * 1 / 1000,
                                           'y': self.cfg.imaging_specs[f'volume_y_um'] * 1 / 1000,
                                           'z': self.cfg.imaging_specs[f'volume_z_um'] * 1 / 1000})
        self.scan_vol.setSize(**scanning_volume)
        self.plot.addItem(self.scan_vol)

        # axis
        # x = gl.GLBoxItem()
        # x.translate(self.origin['x'], self.origin['y'], -up['Z'])
        # x.setSize(x=33,y=0,z=0)
        # x.setColor(qtpy.QtGui.QColor('cornflowerblue'))
        # self.plot.addItem(x)
        # y = gl.GLBoxItem()
        # y.translate(self.origin['x'], self.origin['y'], -up['Z'])
        # y.setSize(x=0, y=33, z=0)
        # y.setColor(qtpy.QtGui.QColor('red'))
        # z = gl.GLBoxItem()
        # self.plot.addItem(y)
        # z.translate(self.origin['x'], self.origin['y'], -up['Z'])
        # z.setSize(x=0, y=0, z=33)
        # z.setColor(qtpy.QtGui.QColor('green'))
        # self.plot.addItem(z)

        # Representing stage position
        self.pos = gl.GLScatterPlotItem(pos=(1, 0, 0), size=1, color=(1.0, 0.0, 0.0, 0.5), pxMode=False)
        self.plot.addItem(self.pos)

        return self.plot
