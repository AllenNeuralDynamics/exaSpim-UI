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
        self.tiles = {}         # Tile in sample pose coords
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
            self.grid_step_um['x'], self.grid_step_um['y'] = self.instrument.get_xy_grid_step(self.cfg.tile_overlap_x_percent,
                                                                                        self.cfg.tile_overlap_y_percent)
            # Tile in sample pose coords
            self.tiles['x'], self.tiles['y'], self.tiles['z'] = self.instrument.get_tile_counts(self.cfg.tile_overlap_x_percent,
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

        coord = (self.map_pose['X'], self.map_pose['Y'], -self.map_pose['Z']) if not self.instrument.simulated else \
            np.random.randint(1000, 60000, 3)
        coord = [i * 0.0001 for i in coord]  # converting from 1/10um to mm
        hue = str(self.map['color'].currentText())
        point = gl.GLScatterPlotItem(pos=coord, size=.2, color=qtpy.QtGui.QColor(hue), pxMode=False)
        info = self.map['label'].text()
        info_point = gl.GLTextItem(pos=coord, text=info, font=qtpy.QtGui.QFont('Helvetica', 10))
        self.plot.addItem(info_point)
        self.plot.addItem(point)

        self.map['label'].clear()

    @thread_worker
    def _map_pos_worker(self):
        """Update position of stage for tissue map"""

        while True:
            try:
                self.map_pose = self.instrument.tigerbox.get_position()

                coord = (
                self.map_pose['X'], self.map_pose['Y'], -self.map_pose['Z'])  # if not self.instrument.simulated \
                #     else np.random.randint(-60000, 60000, 3)
                coord = [i * 0.0001 for i in coord]  # converting from 1/10um to mm
                self.pos.setData(pos=coord)

                if self.instrument.start_pos == None:
                    self.plot.removeItem(self.scan_vol)
                    self.scan_vol = self.draw_volume([coord[0],
                                                      coord[1]-(.5* 0.001*(self.cfg.tile_specs[f'{self.og_axis_remap["y"]}_field_of_view_um'])),
                                                      coord[2]+(.5*0.001*(self.cfg.tile_specs[f'{self.og_axis_remap["z"]}_field_of_view_um']))],
                            (self.cfg.imaging_specs[f'volume_{self.og_axis_remap["x"]}_um'] * 1 / 1000,
                             self.cfg.imaging_specs[f'volume_{self.og_axis_remap["y"]}_um'] * 1 / 1000,
                             -self.cfg.imaging_specs[f'volume_{self.og_axis_remap["z"]}_um'] * 1 / 1000))
                    self.plot.addItem(self.scan_vol)

                    if self.map['tiling'].isChecked():
                        self.draw_tiles([coord[0],
                                                      coord[1]-(.5* 0.001*(self.cfg.tile_specs[f'{self.og_axis_remap["y"]}_field_of_view_um'])),
                                                      coord[2]+(.5*0.001*(self.cfg.tile_specs[f'{self.og_axis_remap["z"]}_field_of_view_um']))])

                else:
                    #   What coordinate system is start pos?
                    start = [self.instrument.start_pos['X'] * 0.0001,
                             ((self.instrument.start_pos['Y']* 0.0001)-(.5*self.cfg.tile_specs[f'{self.og_axis_remap["y"]}_field_of_view_um'])) * 0.001,
                             ((-self.instrument.start_pos['Z']* 0.0001)+(.5*self.cfg.tile_specs[f'{self.og_axis_remap["z"]}_field_of_view_um'])) * 0.001]
                    if self.map['tiling'].isChecked():
                        self.draw_tiles(start)
                    self.draw_volume(start, (self.cfg.imaging_specs[f'volume_{self.og_axis_remap["x"]}_um'] * 1 / 1000,
                             self.cfg.imaging_specs[f'volume_{self.og_axis_remap["y"]}_um'] * 1 / 1000,
                             -self.cfg.imaging_specs[f'volume_{self.og_axis_remap["z"]}_um'] * 1 / 1000))
            except:
                sleep(2)
            finally:
                sleep(.5)
                yield

    def draw_tiles(self, coord):

        if self.initial_volume != [self.cfg.volume_x_um, self.cfg.volume_y_um, self.cfg.volume_z_um]:
            self.set_tiling(2)
            self.initial_volume = [self.cfg.volume_x_um, self.cfg.volume_y_um, self.cfg.volume_z_um]

        for item in self.plot.items:
            if type(item) == gl.GLBoxItem and item != self.scan_vol:
                self.plot.removeItem(item)
        # TODO: This needs to be more generalized because we are assuming the tiger x coordinate has no gridstep
        #   Do this another time in draw volume. make a function? Try finally?
        for y in range(0, self.tiles[self.og_axis_remap['y']]):
            for z in range(0, self.tiles[self.og_axis_remap['z']]):
                tile = self.draw_volume([coord[0],
                                         round(y * self.grid_step_um[self.og_axis_remap['y']] * .001) +coord[1],
                                         round(z * -self.grid_step_um[self.og_axis_remap['z']] * .001) +coord[2]],
                                        [0,self.cfg.tile_specs[f'{self.og_axis_remap["y"]}_field_of_view_um'] * .001,
                                         -self.cfg.tile_specs[f'{self.og_axis_remap["z"]}_field_of_view_um'] * .001])
                tile.setColor(qtpy.QtGui.QColor('cornflowerblue'))
                self.plot.addItem(tile)

    def draw_volume(self, coord: list, size):

        """Redraw and translate volumetric scan box in map"""

        box = gl.GLBoxItem()  # Representing scan volume
        box.translate(*coord)
        box.setSize(*size)
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

    def graph(self):

        self.plot = gl.GLViewWidget()
        self.plot.opts['distance'] = 40

        dirs = ['x', 'y', 'z']
        low = {'X': 0, 'Y': 0, 'Z': 0} if self.instrument.simulated else \
            self.instrument.tigerbox.get_lower_travel_limit(*dirs)
        up = {'X': 60, 'Y': 60, 'Z': 60} if self.instrument.simulated else \
            self.instrument.tigerbox.get_upper_travel_limit(*dirs)

        axes_len = {}
        for directions in dirs:
            axes_len[directions] = up[directions.upper()] - low[directions.upper()]
            self.origin[directions] = low[directions.upper()] + (axes_len[directions] / 2)

        self.plot.opts['center'] = QtGui.QVector3D(self.origin['x'], self.origin['y'], -self.origin['z'])

        # x axes: Translate axis so origin of graph translate to center of stage limits
        # Z coords increase as stage moves down so z origin and coords are negative
        self.create_axes((90, 0, 1, 0),
                         (round(axes_len['z']), round(axes_len['y'])),
                         (low['X'], self.origin['y'], -self.origin['z']))

        # y axes: Translate to lower end of y and origin of x and -z
        self.create_axes((90, 1, 0, 0),
                         (round(axes_len['x']), round(axes_len['z'])),
                         (self.origin['x'], low['Y'], -self.origin['z']))

        # z axes: Translate to origin of x, y, z
        self.create_axes((0, 0, 0, 0),
                         (round(axes_len['x']), round(axes_len['y'])),
                         (self.origin['x'], self.origin['y'], -up['Z']))

        # Representing scan volume
        self.scan_vol = gl.GLBoxItem()
        self.scan_vol.translate(self.origin['x'], self.origin['y'], -up['Z'])
        self.scan_vol.setSize(x=self.cfg.imaging_specs[f'volume_x_um'] * 1 / 1000,
                              y=self.cfg.imaging_specs[f'volume_y_um'] * 1 / 1000,
                              z=self.cfg.imaging_specs[f'volume_z_um'] * 1 / 1000)
        self.plot.addItem(self.scan_vol)

        # #axis
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


