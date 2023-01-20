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

        self.scan_tiles = [None]
        self.initial_volume = [self.cfg.volume_x_um, self.cfg.volume_y_um, self.cfg.volume_z_um]

    def set_tab_widget(self, tab_widget: QTabWidget):

        self.tab_widget = tab_widget
        self.tab_widget.tabBarClicked.connect(self.stage_positon_map)

    def stage_positon_map(self, index):
        last_index = len(self.tab_widget) - 1
        if index == last_index:
            self.map_pos_worker = self._map_pos_worker()
            self.map_pos_worker.start()
            # TODO: Start stage position worker
            # if start position is not none, update start position, volume, and
            # outline box which is going to be image

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

        if state == 2:
            self.x_grid_step_um, self.y_grid_step_um = self.instrument.get_xy_grid_step(self.cfg.tile_overlap_x_percent,
                                                                                        self.cfg.tile_overlap_y_percent)

            self.xtiles, self.ytiles, self.ztiles = self.instrument.get_tile_counts(self.cfg.tile_overlap_x_percent,
                                                                                    self.cfg.tile_overlap_y_percent,
                                                                                    self.cfg.z_step_size_um,
                                                                                    self.cfg.volume_x_um,
                                                                                    self.cfg.volume_y_um,
                                                                                    self.cfg.volume_z_um)

        if state == 0:
            for tiles in self.scan_tiles: self.plot.removeItem(tiles)

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
        sleep(1)  # Pause to allow stage to complete any task before asking where it is
        while True:
            try:
                self.map_pose = self.instrument.sample_pose.get_position()
                coord = (
                self.map_pose['X'], self.map_pose['Y'], -self.map_pose['Z'])  # if not self.instrument.simulated \
                #     else np.random.randint(-60000, 60000, 3)
                coord = [i * 0.0001 for i in coord]  # converting from 1/10um to mm
                self.pos.setData(pos=coord)

                if self.instrument.start_pos == None:
                    self.plot.removeItem(self.scan_vol)
                    self.scan_vol = self.draw_volume(coord, (self.cfg.imaging_specs[f'volume_x_um'] * 1 / 1000,
                                                             self.cfg.imaging_specs[f'volume_y_um'] * 1 / 1000,
                                                             self.cfg.imaging_specs[f'volume_z_um'] * 1 / 1000))
                    self.plot.addItem(self.scan_vol)

                    if self.map['tiling'].isChecked():
                        self.draw_tiles(coord)

                else:
                    start = [self.instrument.start_pos['X'] * 0.0001,
                             self.instrument.start_pos['Y'] * 0.0001,
                             -self.instrument.start_pos['Z'] * 0.0001]
                    if self.map['tiling'].isChecked():
                        self.draw_tiles(start)
                    self.draw_volume(start, [self.cfg.volume_x_um * .001,
                                             self.cfg.volume_x_um * .001,
                                             self.cfg.volume_x_um * .001])
            finally:
                sleep(.5)
                yield

    def draw_tiles(self, coord):

        if self.initial_volume != [self.cfg.volume_x_um, self.cfg.volume_y_um, self.cfg.volume_z_um]:
            print('changed volumes')
            self.set_tiling(2)
            print(f'x tiles: {self.xtiles} y tiles: {self.ytiles}')
            self.initial_volume = [self.cfg.volume_x_um, self.cfg.volume_y_um, self.cfg.volume_z_um]

        for x in range(0, self.xtiles):
            tile = self.draw_volume([round(x *self.x_grid_step_um * .001) + coord[0],
                                     round(self.y_grid_step_um * .001) + coord[1], coord[2]],
                                    [self.cfg.tile_specs['x_field_of_view_um'] * .001,
                                     self.cfg.tile_specs['y_field_of_view_um'] * .001, 0])
            tile.setColor(qtpy.QtGui.QColor('cornflowerblue'))
            self.scan_tiles.append(tile)

        for y in range(0, self.ytiles):
            tile = self.draw_volume([round(self.x_grid_step_um * .001) + coord[0],
                                     round(y*self.y_grid_step_um * .001) + coord[1], coord[2]],
                                    [self.cfg.tile_specs['x_field_of_view_um'] * .001,
                                     self.cfg.tile_specs['y_field_of_view_um'] * .001, 0])
            tile.setColor(qtpy.QtGui.QColor('coral'))
            self.scan_tiles.append(tile)

        for tiles in self.scan_tiles: self.plot.removeItem(tiles) \
            if tiles in self.plot.items else self.plot.addItem(tiles)

        del self.scan_tiles[0:len(self.scan_tiles) - (self.xtiles+self.ytiles)]

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

    def create_axes(self, rotation, size, translate):

        axes = gl.GLGridItem()
        axes.rotate(*rotation)
        axes.setSize(*size)
        axes.translate(*translate)  # Translate to lower end of x and origin of y and -z
        self.plot.addItem(axes)

    def rotate_graph(self, click, center, elevation, azimuth):

        """Rotate graph to specific view"""

        self.plot.opts['center'] = center
        self.plot.opts['elevation'] = elevation
        self.plot.opts['azimuth'] = azimuth

    def graph(self):

        self.plot = GraphItem()
        self.plot.opts['distance'] = 40

        dirs = ['x', 'y', 'z']
        low = {'X': 0, 'Y': 0, 'Z': 0} if self.instrument.simulated else \
            self.instrument.sample_pose.get_lower_travel_limit(*dirs)
        up = {'X': 60, 'Y': 60, 'Z': 60} if self.instrument.simulated else \
            self.instrument.sample_pose.get_upper_travel_limit(*dirs)
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

        # Representing stage position
        self.pos = gl.GLScatterPlotItem(pos=(1, 0, 0), size=1, color=(1.0, 0.0, 0.0, 0.5), pxMode=False)
        self.plot.addItem(self.pos)

        # Representing tiles
        self.scan_tiles[0] = gl.GLBoxItem(size=QtGui.QVector3D(0, 0, 0))
        self.plot.addItem(self.scan_tiles[0])

        return self.plot

    # def upload_graph(self):
    #
    #     file = open(r'C:\Users\micah.woodard\Downloads\test1.txt', 'r+')
    #     elements = [line.rstrip('\n') for line in file.readlines()]
    #
    #     try:
    #         points = np.genfromtxt(elements[1:elements.index('color')])
    #         colors = np.genfromtxt(elements[elements.index('color') + 1:elements.index('text')])
    #         text = elements[elements.index('text') + 1:elements.index('text pos')]
    #         text_pos = np.genfromtxt(elements[elements.index('text pos') + 1:len(elements)])
    #         text_pos = [np.array(x) for x in text_pos]
    #
    #     except:
    #         self.error_msg('Invalid Map','Invalid map format. Example format:\n points\n 0 0 0 \n 1 1 1\ncolor\n '
    #                                      '1 1 1 1 \n 0 1 0 1\n text\n hello \ntext pos\n 0 0 0' )
    #         print('invalid format. format goes points\ncolor\ntext\ntext pos\n')
    #
    #
    #     p1 = gl.GLScatterPlotItem(pos=points, size=2, color=colors)
    #     w.addItem(p1)
    #
    #     for words, points in zip(text, text_pos):
    #         info_point = gl.GLTextItem(pos=points, text=words, font=qtpy.QtGui.QFont('Helvetica', 10))
    #         w.addItem(info_point)


class GraphItem(gl.GLViewWidget):

    def __init__(self):
        super().__init__()

    # def mouseReleaseEvent(self, e):
    #     super().mousePressEvent(e)
    #
    #     items = self.itemsAt((e.pos().x() - 5, e.pos().y() - 5, 10, 10))
    #     if len(items) == 0:
    #         return
    #     print(items)
    #     for item in items:
    #         if type(item) == gl.GLScatterPlotItem:
    #
    #             return_value = self.delete_point_warning()
    #             if return_value == QMessageBox.Cancel:
    #                 return
    #
    #             self.removeItem(item)
    #     e.accept()
    #
    # def delete_point_warning(self):
    #     msgBox = QMessageBox()
    #     msgBox.setIcon(QMessageBox.Information)
    #     msgBox.setText("Do you want to delete this point?")
    #     msgBox.setWindowTitle("Delete Point")
    #     msgBox.setStandardButtons(QMessageBox.Ok | QMessageBox.Cancel)
    #     return msgBox.exec()
