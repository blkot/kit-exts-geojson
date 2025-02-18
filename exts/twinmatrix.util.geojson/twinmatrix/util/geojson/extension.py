import omni.ext
import omni.ui as ui
import json
import carb.tokens
import omni.kit.commands
from pxr import Gf, UsdGeom, Sdf
import math


# Functions and vars are available to other extension as usual in python: `example.python_ext.some_public_function(x)`
def some_public_function(x: int):
    print("[twinmatrix.util.geojson] some_public_function was called with x: ", x)
    return x ** x


class GeoJSONData:
    def __init__(self):
        self.features = []
        self.bounds = None
        
    def load_from_file(self, file_path: str):
        try:
            print(f"Attempting to load file: {file_path}")  # 添加日志
            with open(file_path, 'r') as f:
                data = json.load(f)
            
            print(f"File content type: {data.get('type', 'unknown')}")  # 添加日志
            
            # 检查是否为 FeatureCollection 或其他有效类型
            valid_types = ["FeatureCollection", "Feature"]
            if data.get("type") not in valid_types:
                raise ValueError(f"Unsupported GeoJSON type: {data.get('type')}. Supported types: {valid_types}")
            
            # 如果是单个Feature，将其转换为FeatureCollection
            if data["type"] == "Feature":
                self.features = [data]
            else:
                self.features = data.get("features", [])
            
            print(f"Loaded feature count: {len(self.features)}")  # 添加日志
            
            # 计算边界框
            self._calculate_bounds()
            return True
            
        except FileNotFoundError:
            print(f"File not found: {file_path}")
            return False
        except json.JSONDecodeError as e:
            print(f"JSON parsing error: {str(e)}")
            return False
        except KeyError as e:
            print(f"GeoJSON format error, missing key field: {str(e)}")
            return False
        except Exception as e:
            print(f"Error loading GeoJSON: {str(e)}")
            return False
            
    def _calculate_bounds(self):
        if not self.features:
            self.bounds = None
            return
            
        min_x = min_y = float('inf')
        max_x = max_y = float('-inf')
        
        for feature in self.features:
            coords = self._get_feature_coordinates(feature)
            for coord in coords:
                min_x = min(min_x, coord[0])
                max_x = max(max_x, coord[0])
                min_y = min(min_y, coord[1])
                max_y = max(max_y, coord[1])
                
        self.bounds = {
            "min": (min_x, min_y),
            "max": (max_x, max_y)
        }
        
    def _get_feature_coordinates(self, feature):
        coords = []
        geometry = feature["geometry"]
        if geometry["type"] == "Point":
            coords.append(geometry["coordinates"])
        elif geometry["type"] == "LineString":
            coords.extend(geometry["coordinates"])
        elif geometry["type"] == "Polygon":
            for ring in geometry["coordinates"]:
                coords.extend(ring)
        return coords


# Any class derived from `omni.ext.IExt` in top level module (defined in `python.modules` of `extension.toml`) will be
# instantiated when extension gets enabled and `on_startup(ext_id)` will be called. Later when extension gets disabled
# on_shutdown() is called.
class TwinmatrixUtilGeojsonExtension(omni.ext.IExt):
    # ext_id is current extension id. It can be used with extension manager to query additional information, like where
    # this extension is located on filesystem.
    def on_startup(self, ext_id):
        print("[twinmatrix.util.geojson] twinmatrix util geojson startup")
        
        self._geojson_data = GeoJSONData()
        self._window = ui.Window("GeoJSON Utility", width=400, height=400, visible=False)  # 初始设置为不可见
        
        # 添加菜单项
        self._menu_path = "Window/GeoJSON Utility"
        editor_menu = omni.kit.ui.get_editor_menu()
        if editor_menu:
            self._menu = editor_menu.add_item(
                self._menu_path, 
                self._on_menu_click, 
                toggle=True, 
                value=False
            )
        
        # 设置窗口关闭回调
        self._window.set_visibility_changed_fn(self._on_window_visibility_changed)
        
        with self._window.frame:
            with ui.VStack(spacing=10):
                with ui.CollapsableFrame("Import GeoJSON"):
                    with ui.VStack(spacing=5):
                        ui.Label("Select GeoJSON file:", height=20)
                        with ui.HStack(spacing=5, height=20):
                            # Add default debug path
                            default_path = r"H:\GeoJSON\small\3poly.geojson"
                            self._file_path = ui.StringField(
                                width=ui.Fraction(0.7),
                                height=0
                            )
                            self._file_path.model.set_value(default_path)  # Set default value
                            ui.Button("Browse", 
                                    width=ui.Fraction(0.3), 
                                    clicked_fn=lambda: self._on_browse())
                        ui.Button("Import", 
                                height=20,
                                clicked_fn=lambda: self._on_import())
                        self._status_label = ui.Label("", height=20)

                # 添加数据信息显示部分
                with ui.CollapsableFrame("GeoJSON Information"):
                    with ui.VStack(spacing=5):
                        self._feature_count_label = ui.Label("Features: 0", height=20)
                        self._bounds_label = ui.Label("Bounds: None", height=40, word_wrap=True)
                        self._geometry_types_label = ui.Label("Geometry Types: None", height=40, word_wrap=True)

    def _on_browse(self):
        from omni.kit.window.file_importer import get_file_importer
        
        def import_handler(filename: str, dirname: str, selections: list = []):
            if filename:
                self._file_path.model.set_value(filename)
        
        file_importer = get_file_importer()
        file_importer.show_window(
            title="Select GeoJSON File",
            import_handler=import_handler,
            file_extension_options=[".json", ".geojson"]
        )

    def _on_import(self):
        file_path = self._file_path.model.get_value_as_string()
        if not file_path:
            self._status_label.text = "Please select a file first"
            return
            
        if self._geojson_data.load_from_file(file_path):
            self._status_label.text = "GeoJSON loaded successfully"
            self._update_info_display()
            self._create_stage_objects()
        else:
            self._status_label.text = "Failed to load GeoJSON"
            
    def _update_info_display(self):
        """更新GeoJSON信息显示"""
        # 更新要素数量
        feature_count = len(self._geojson_data.features)
        self._feature_count_label.text = f"Features: {feature_count}"
        
        # 更新边界框信息
        if self._geojson_data.bounds:
            min_coord = self._geojson_data.bounds["min"]
            max_coord = self._geojson_data.bounds["max"]
            bounds_text = f"Bounds: Min({min_coord[0]:.4f}, {min_coord[1]:.4f}), Max({max_coord[0]:.4f}, {max_coord[1]:.4f})"
        else:
            bounds_text = "Bounds: None"
        self._bounds_label.text = bounds_text
        
        # 统计几何类型
        geometry_types = set()
        for feature in self._geojson_data.features:
            if "geometry" in feature and feature["geometry"]:
                geometry_types.add(feature["geometry"]["type"])
        
        if geometry_types:
            types_text = "Geometry Types: " + ", ".join(sorted(geometry_types))
        else:
            types_text = "Geometry Types: None"
        self._geometry_types_label.text = types_text
    def _geo_to_cartesian(self, lon, lat):
        """将 WGS84 地理坐标（经纬度）转换为 Y-up 笛卡尔坐标系
        使用 Web Mercator 投影 (EPSG:3857)
        注意：Omniverse 使用右手坐标系，Y 轴朝上
        - X: 东向为正
        - Y: 上向为正
        - Z: 南向为正
        """
        # WGS84 椭球体参数
        a = 6378137.0  # 长半轴（赤道半径）
        e = 0.081819190842622  # 第一偏心率
        
        # 将经纬度转换为弧度
        lon_rad = math.radians(lon)
        lat_rad = math.radians(lat)
        
        # Web Mercator 投影公式
        x = a * lon_rad
        z = -a * math.log(math.tan(math.pi/4 + lat_rad/2) * 
                         math.pow((1 - e * math.sin(lat_rad))/(1 + e * math.sin(lat_rad)), e/2))
        
        return x, 0, z  # 返回 (x, y, z)，y=0 表示在地平面上

    def _triangulate_polygon(self, points):
        """Triangulate polygon following GeoJSON right-hand rule
        GeoJSON polygons: 
        - Exterior rings are counterclockwise (right-hand rule)
        - Interior rings are clockwise
        - Rings are closed (first and last points are identical)
        """
        if len(points) < 3:
            return []
            
        # Ensure polygon is closed
        if points[0] != points[-1]:
            points.append(points[0])
            
        # Remove the duplicate end point for triangulation
        vertices = points[:-1]
        if len(vertices) < 3:
            return []
            
        indices = []
        remaining = list(range(len(vertices)))
        
        def get_area():
            """Calculate signed area to determine polygon orientation"""
            area = 0
            for i in range(len(vertices) - 1):
                j = (i + 1)
                area += vertices[i][0] * vertices[j][2] - vertices[j][0] * vertices[i][2]
            return area / 2
            
        def is_valid_ear(i):
            """Check if vertex i forms a valid ear"""
            size = len(remaining)
            if size < 3:
                return False
                
            prev_idx = remaining[(remaining.index(i) - 1) % size]
            next_idx = remaining[(remaining.index(i) + 1) % size]
            
            p1 = vertices[prev_idx]
            p2 = vertices[i]
            p3 = vertices[next_idx]
            
            # Check if triangle follows right-hand rule (counterclockwise)
            v1 = Gf.Vec3d(p2[0] - p1[0], p2[1] - p1[1], p2[2] - p1[2])
            v2 = Gf.Vec3d(p3[0] - p2[0], p3[1] - p2[1], p3[2] - p2[2])
            cross = Gf.Cross(v1, v2)
            
            # Triangle should point up (Y positive) for proper orientation
            if cross[1] <= 0:
                return False
                
            # Check if any remaining vertex is inside this triangle
            for j in remaining:
                if j in (prev_idx, i, next_idx):
                    continue
                    
                p = vertices[j]
                if self._point_in_triangle(p, p1, p2, p3):
                    return False
                    
            return True
            
        # Main triangulation loop
        while len(remaining) > 3:
            found_ear = False
            for i in remaining:
                if is_valid_ear(i):
                    # Add triangle indices
                    idx = remaining.index(i)
                    prev_idx = remaining[(idx - 1) % len(remaining)]
                    next_idx = remaining[(idx + 1) % len(remaining)]
                    indices.extend([prev_idx, i, next_idx])
                    
                    # Remove the ear vertex
                    remaining.remove(i)
                    found_ear = True
                    break
                    
            if not found_ear:
                print("Warning: Failed to find valid ear, breaking")
                break
                
        # Add final triangle
        if len(remaining) == 3:
            indices.extend(remaining)
            
        return indices
        
    def _point_in_triangle(self, p, a, b, c):
        """Check if point p is inside triangle abc"""
        def sign(p1, p2, p3):
            return (p1[0] - p3[0]) * (p2[2] - p3[2]) - (p2[0] - p3[0]) * (p1[2] - p3[2])
            
        d1 = sign(p, a, b)
        d2 = sign(p, b, c)
        d3 = sign(p, c, a)
        
        has_neg = (d1 < 0) or (d2 < 0) or (d3 < 0)
        has_pos = (d1 > 0) or (d2 > 0) or (d3 > 0)
        
        return not (has_neg and has_pos)

    def _create_stage_objects(self):
        """Create USD objects from GeoJSON data"""
        stage = omni.usd.get_context().get_stage()
        if not stage:
            print("Failed to get USD stage")
            return

        print(f"Start processing GeoJSON data with {len(self._geojson_data.features)} features")
        
        # Create root Xform
        geojson_path = "/World/GeoJSON"
        geojson_xform = UsdGeom.Xform.Define(stage, geojson_path)
        
        # 计算投影后的边界框
        bounds_cart = {
            "min": [float('inf'), 0, float('inf')], 
            "max": [float('-inf'), 0, float('-inf')]
        }
        
        for feature in self._geojson_data.features:
            geometry = feature.get("geometry", {})
            if geometry.get("type") == "Polygon":
                for coord in geometry.get("coordinates", [[]])[0]:
                    x, y, z = self._geo_to_cartesian(coord[0], coord[1])
                    bounds_cart["min"][0] = min(bounds_cart["min"][0], x)
                    bounds_cart["min"][2] = min(bounds_cart["min"][2], z)
                    bounds_cart["max"][0] = max(bounds_cart["max"][0], x)
                    bounds_cart["max"][2] = max(bounds_cart["max"][2], z)
        
        # 计算中心点和缩放
        center_x = (bounds_cart["min"][0] + bounds_cart["max"][0]) / 2
        center_z = (bounds_cart["min"][2] + bounds_cart["max"][2]) / 2
        
        # 计算合适的缩放因子
        width = bounds_cart["max"][0] - bounds_cart["min"][0]
        depth = bounds_cart["max"][2] - bounds_cart["min"][2]
        scale = 1.0 / max(width, depth) * 1000  # 将最大尺寸缩放到1000单位
        
        # 设置根节点的变换（修改这部分）
        xformable = UsdGeom.Xformable(geojson_xform)
        
        # 检查是否已存在变换操作
        if not xformable.GetOrderedXformOps():
            # 只有在没有现有变换操作时才添加新的操作
            translate_op = xformable.AddTranslateOp()
            scale_op = xformable.AddScaleOp()
            
            translate_op.Set(Gf.Vec3d(-center_x * scale, 0, -center_z * scale))
            scale_op.Set(Gf.Vec3d(scale, scale, scale))
        
        for i, feature in enumerate(self._geojson_data.features):
            geometry = feature.get("geometry", {})
            geo_type = geometry.get("type", "Unknown")
            print(f"\nProcessing feature {i + 1}/{len(self._geojson_data.features)}")
            print(f"Geometry type: {geo_type}")
            
            if geo_type == "Polygon":
                rings = geometry.get("coordinates", [])
                print(f"Polygon contains {len(rings)} rings")
                
                # Get outer ring coordinates
                outer_ring = rings[0]
                print(f"Outer ring contains {len(outer_ring)} coordinate points")
                
                if len(outer_ring) < 3:
                    print("Warning: Less than 3 coordinate points, skipping this polygon")
                    continue
                
                # Convert coordinates to Y-up system
                points = []
                for j, coord in enumerate(outer_ring):
                    x, y, z = self._geo_to_cartesian(coord[0], coord[1])
                    points.append(Gf.Vec3f(x, y, z))
                print(f"Converted {len(points)} points to Cartesian coordinates")
                
                # Create mesh
                poly_path = f"{geojson_path}/polygon_{i}"
                print(f"Creating mesh: {poly_path}")
                
                poly_xform = UsdGeom.Xform.Define(stage, poly_path)
                mesh = UsdGeom.Mesh.Define(stage, f"{poly_path}/mesh")
                
                # Triangulate and create mesh
                face_indices = self._triangulate_polygon(points[:])
                if face_indices:
                    triangle_count = len(face_indices) // 3
                    print(f"Generated {triangle_count} triangles")
                    
                    mesh.CreatePointsAttr(points)
                    face_vertex_counts = [3] * triangle_count
                    mesh.CreateFaceVertexCountsAttr(face_vertex_counts)
                    mesh.CreateFaceVertexIndicesAttr(face_indices)
                    
                    normals = [Gf.Vec3f(0, 1, 0)] * len(points)
                    mesh.CreateNormalsAttr(normals)
                    
                    mesh.CreateDisplayColorAttr([Gf.Vec3f(0.8, 0.8, 0.8)])
                    mesh.CreateSubdivisionSchemeAttr().Set(UsdGeom.Tokens.none)
                    mesh.CreateDoubleSidedAttr().Set(True)
                    print(f"Mesh creation completed: {len(points)} vertices, {triangle_count} triangles")
                else:
                    print("Warning: Triangulation failed, mesh not created")
            
            elif geo_type == "MultiPolygon":
                print(f"MultiPolygon contains {len(geometry.get('coordinates', []))} polygons")
                # TODO: Add MultiPolygon processing logic
            else:
                print(f"Skipping unsupported geometry type: {geo_type}")

        print("\nProcessing completed")
        print(f"Total processed features: {len(self._geojson_data.features)}")

    def _on_menu_click(self, menu, value):
        """处理菜单点击事件"""
        self._window.visible = value
        
    def _on_window_visibility_changed(self, visible):
        """处理窗口可见性变化"""
        editor_menu = omni.kit.ui.get_editor_menu()
        if editor_menu:
            editor_menu.set_value(self._menu_path, visible)

    def on_shutdown(self):
        print("[twinmatrix.util.geojson] twinmatrix util geojson shutdown")
        # 移除菜单项
        editor_menu = omni.kit.ui.get_editor_menu()
        if editor_menu:
            editor_menu.remove_item(self._menu_path)
        
        # 清理窗口
        self._window = None
