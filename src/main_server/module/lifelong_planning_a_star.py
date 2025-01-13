import heapq
import math
import traceback

import numpy as np
from anyio import value
from sympy import symbols, Eq, solve
import networkx as nx
import matplotlib.pyplot as plt


def closer_axis_and_intersections(a, p1, p2):
    x, y = symbols('x y')

    # 첫 번째 선의 두 점 (x1, y1), (x2, y2) 설정
    x1, y1 = p1  # 첫 번째 점
    x2, y2 = p2  # 두 번째 점

    # 두 번째 선이 지나는 점 (ax, ay)
    ax, ay = a

    # 두 번째 선의 기울기 m2 (m1의 음의 역수)
    # p1, p2를 지나는 직선의 기울기
    if x1 == x2:
        # 직선이 수직인 경우 (x = 일정 값)
        return x1, ay  # 수직선에서 교점은 (x1, ay)
    if y1 == y2:
        # 직선이 수평선인 경우 (y = 일정 값)
        return ax, y1  # 수평선에서 교점은 (ax, y1)
    # 첫 번째 선의 기울기 m1
    m1 = (y2 - y1) / (x2 - x1)

    # 첫 번째 선의 방정식: y = m1 * (x - x1) + y1
    line1 = Eq(y, m1 * (x - x1) + y1)

    m2 = -1 / m1

    # 두 번째 선의 방정식: y = m2 * (x - ax) + ay
    line2 = Eq(y, m2 * (x - ax) + ay)

    # 두 방정식의 교점을 구함
    solution = solve([line1, line2], (x, y))
    return solution[x], solution[y]


def angle_difference(deg1, deg2):
    if deg1 == 0.01:
        deg1 = deg2
    elif deg2 == 0.01:
        deg2 = deg1

    # 각도를 0~360 범위로 정규화
    deg1 = deg1 % 360
    deg2 = deg2 % 360

    # 두 각도의 차이 계산 (절대값으로)
    diff = abs(deg1 - deg2)

    # 차이가 180도를 넘으면 반대 방향에서 접근
    if diff > 180:
        diff = 360 - diff

    # 차이를 라디안으로 변환
    rad_diff = math.radians(diff)

    return rad_diff


class Node:
    def __init__(self, number, x=0, y=0, angle=0, command_data=None, description="", display=""):
        if command_data is None:
            command_data = {}
        self.name = number
        self.x = x
        self.y = y
        self.a = angle
        self.g = float('inf')  # Cost from start to this node
        self.h = 0  # Heuristic cost estimate to goal
        self.f = float('inf')  # Total cost (g + h)
        self.o = {}        # 장애물 여부
        self.parent = None
        self.command_data = command_data
        self.description = description
        self.display = display

    def __lt__(self, other):
        return self.f < other.f


class Graph:
    def __init__(self):
        self.nodes: dict[any, Node] = {}
        self.edges = {}
        self.edge_command_data = {}
        self.edge_range = {}
        self.work_zone = {}
        self.node_display = {}

    def get_node_display(self, description):
        """노드 표시 가져오기"""
        return self.node_display.get(description, (None, description))[1]

    def get_node_idx(self, description):
        """노드 표시 가져오기"""
        return self.node_display.get(description, (None, description))[0]

    def add_node(self, name, x=0, y=0, angle=0, command_data=None, description="", display=""):
        """노드에 좌표를 추가하여 휴리스틱 계산에 사용"""
        if self.nodes.get(name) is None:
            node = Node(name, x, y, angle, command_data, description, display)
            self.nodes[name] = node
        else:
            if command_data is None:
                command_data = {}
            self.nodes[name].x = x
            self.nodes[name].y = y
            self.nodes[name].a = angle
            self.nodes[name].command_data = command_data
            self.nodes[name].name = name
            self.nodes[name].description = description
            self.nodes[name].display = display

        # 간선 정보 초기화
        self.edges[name] = {}
        self.edge_range[name] = {}
        self.edge_command_data[name] = {}
        self.work_zone[name] = {}
        self.node_display[description] = (name, display)

    def add_edge(self, from_node, to_node, cost=1, command_data=None, range_data=None, work_zone=False):
        if command_data is None:
            command_data = {}
        if self.edges.get(from_node) is not None:
            self.edges[from_node][to_node] = cost
            self.edge_command_data[from_node][to_node] = command_data
            self.edge_range[from_node][to_node] = range_data
            self.work_zone[from_node][to_node] = work_zone

    def remove_node(self, node_name):
        del self.nodes[node_name]
        del self.edges[node_name]
        del self.edge_command_data[node_name]
        del self.edge_range[node_name]
        del self.work_zone[node_name]

    def remove_edge(self, edges):
        for from_node, to_node in edges:
            if self.edges.get(from_node) is not None:
                if self.edges[from_node].get(to_node) is not None:
                    del self.edges[from_node][to_node]

    def add_obstacle_node(self, module_name, obstacle_node):
        if self.nodes.get(obstacle_node) is not None:
            self.nodes[obstacle_node].o[module_name] = True

    def remove_obstacle_node(self, module_name, obstacle_node):
        if self.nodes.get(obstacle_node) is not None:
            self.nodes[obstacle_node].o[module_name] = False

    def heuristic(self, node, goal):
        """유클리드 거리를 휴리스틱으로 사용"""
        dx = goal.x - node.x
        dy = goal.y - node.y
        euclidean_distance = math.sqrt(dx * dx + dy * dy)
        da = angle_difference(goal.a, node.a)
        return euclidean_distance + da

    def initialize_nodes(self):
        """모든 노드를 다시 초기화"""
        for node in self.nodes.values():
            node.g = float('inf')
            node.f = float('inf')
            node.parent = None

    # 경로 비용 가져오기
    def get_path_cost(self, path, cost_flag=True):
        cost = 0
        for i in range(1, len(path)):
            from_node = path[i-1]
            to_node = path[i]
            cost += self.heuristic(self.nodes[from_node], self.nodes[to_node])
            if cost_flag is True:
                # 간선 cost 포함
                cost += self.edges[from_node][to_node]
        return cost

    def lpa_star(self, module_name, start, goal, obstacle_check=True, work_zone_possible=False):
        """LPA* 알고리즘을 이용한 경로 탐색"""
        open_set = []
        self.initialize_nodes()  # 탐색할 때마다 노드 초기화

        start_node = self.nodes[start]
        goal_node = self.nodes[goal]

        # 시작 노드 초기화
        start_node.g = 0
        start_node.h = self.heuristic(start_node, goal_node)
        start_node.f = start_node.g + start_node.h

        # open 리스트에 시작 노드를 추가
        heapq.heappush(open_set, start_node)

        while open_set:
            current_node = heapq.heappop(open_set)

            # 목표 노드에 도달하면 경로 재구성
            if current_node.name == goal:
                return self.reconstruct_path(current_node)

            # 인접 노드 탐색
            for neighbor, weight in self.edges[current_node.name].items():
                tentative_g = current_node.g + weight

                # 장애물 확인
                obstacle_flag = False
                if obstacle_check is True:
                    # 장애물 확인이 True라면
                    obstacle_flag = self.is_obstacle_node(module_name, neighbor)

                # 작업 구간 확인
                work_zone_flag = False
                if work_zone_possible is False:
                    # 작업 구간 가능이 False일 경우 작업 구간 가져오기 (작업 구간일 경우 경로 구성에서 제외)
                    work_zone_flag = self.work_zone[current_node.name][neighbor]

                # 더 나은 경로를 찾은 경우
                if tentative_g < self.nodes[neighbor].g and obstacle_flag is False and work_zone_flag is False:
                    self.nodes[neighbor].g = tentative_g
                    self.nodes[neighbor].h = self.heuristic(self.nodes[neighbor], goal_node)
                    self.nodes[neighbor].f = tentative_g + self.nodes[neighbor].h
                    self.nodes[neighbor].parent = current_node
                    if self.nodes[neighbor] not in open_set:
                        heapq.heappush(open_set, self.nodes[neighbor])
        return None

    def reconstruct_path(self, current_node):
        """목표 노드까지의 경로 재구성"""
        path = []
        while current_node:
            path.append(current_node.name)
            current_node = current_node.parent
        return path[::-1]

    # 장애물 노드인지
    def is_obstacle_node(self, module_name, node):
        obstacle_flag = False
        for obstacle_module_name, flag in self.nodes[node].o.items():
            if obstacle_module_name == module_name:
                continue
            if flag is True:
                obstacle_flag = True
                print(module_name, "장애물:", self.nodes[node].name, self.nodes[node].description)
                break
        return obstacle_flag

    # 두 점 사이의 유클리드 거리 계산 함수
    def euclidean_distance(self, node_1, node_2):
        return math.sqrt((node_1[0] - node_2[0]) ** 2 + (node_1[1] - node_2[1]) ** 2)

    # 인접한 노드들 찾기 (deprecated 예정)
    def find_closest_nodes(self, x_axis, y_axis):
        closest_node = {}
        for now_node_name, edge_data in self.edges.items():
            for neighbor_node_name, cost in edge_data.items():
                now_node = self.nodes[now_node_name]
                neighbor_node = self.nodes[neighbor_node_name]

                # 두 노드에서 a까지의 거리 계산
                now_axis: tuple = (x_axis, y_axis)
                node_1: tuple = (now_node.x, now_node.y)
                node_2: tuple = (neighbor_node.x, neighbor_node.y)

                euclidean_node_1 = self.euclidean_distance(now_axis, node_1)
                euclidean_node_2 = self.euclidean_distance(now_axis, node_2)
                if euclidean_node_1 != euclidean_node_2 and euclidean_node_1 <= 0.1:
                    # AGV 위치가 10cm 이하일 경우 1번 노드에 있다고 판단
                    for node_name, node_data in self.nodes.items():
                        # 근처 노드도 포함
                        if self.is_within_expanded_bounds((node_data.x, node_data.y), node_1, None, {}) is True:
                            closest_node[node_name] = True
                    closest_node[now_node_name] = True
                elif euclidean_node_1 != euclidean_node_2 and euclidean_node_2 <= 0.1:
                    # AGV 위치가 10cm 이하일 경우 2번 노드에 있다고 판단
                    for node_name, node_data in self.nodes.items():
                        # 근처 노드도 포함
                        if self.is_within_expanded_bounds((node_data.x, node_data.y), node_2, None, {}) is True:
                            closest_node[node_name] = True
                    closest_node[neighbor_node_name] = True
                elif self.is_within_expanded_bounds(now_axis, node_1, node_2, {}) is True:
                    for node_name, node_data in self.nodes.items():
                        # 간선에 지나가는 노드도 포함
                        if self.is_within_expanded_bounds((node_data.x, node_data.y), node_1, node_2, {}) is True:
                            closest_node[node_name] = True
                    closest_node[now_node_name] = True
                    closest_node[neighbor_node_name] = True
        return closest_node

    # 인접한 노드/간선들 찾기
    def find_closest_graph(self, x_axis, y_axis):
        closest_graph = set()
        for now_node_name, edge_data in self.edges.items():
            for neighbor_node_name, cost in edge_data.items():
                now_node = self.nodes[now_node_name]
                neighbor_node = self.nodes[neighbor_node_name]

                # 두 노드에서 a까지의 거리 계산
                now_axis: tuple = (x_axis, y_axis)
                node_1: tuple = (now_node.x, now_node.y)
                node_2: tuple = (neighbor_node.x, neighbor_node.y)

                euclidean_node_1 = self.euclidean_distance(now_axis, node_1)
                euclidean_node_2 = self.euclidean_distance(now_axis, node_2)
                if euclidean_node_1 != euclidean_node_2 and euclidean_node_1 <= 0.1:
                    # AGV 위치가 10cm 이하일 경우 1번 노드에 있다고 판단
                    for node_name, node_data in self.nodes.items():
                        # 근처 노드도 포함
                        if self.is_within_expanded_bounds((node_data.x, node_data.y), node_1, None, {}) is True:
                            closest_graph.add(node_name)
                    closest_graph.add(now_node_name)
                elif euclidean_node_1 != euclidean_node_2 and euclidean_node_2 <= 0.1:
                    # AGV 위치가 10cm 이하일 경우 2번 노드에 있다고 판단
                    for node_name, node_data in self.nodes.items():
                        # 근처 노드도 포함
                        if self.is_within_expanded_bounds((node_data.x, node_data.y), node_2, None, {}) is True:
                            closest_graph.add(node_name)
                    closest_graph.add(neighbor_node_name)
                elif self.is_within_expanded_bounds(now_axis, node_1, node_2, {}) is True:
                    for node_name, node_data in self.nodes.items():
                        # 간선에 지나가는 노드도 포함
                        if node_name != now_node_name and node_name != neighbor_node_name:
                            # 해당 간선과 연결 되어 있는 노드는 제외
                            if self.is_within_expanded_bounds((node_data.x, node_data.y), node_1, node_2, {}) is True:
                                closest_graph.add(node_name)
                    closest_graph.add((now_node_name, neighbor_node_name))
        return closest_graph

    # 범위 내 있는지 확인
    def is_within_expanded_bounds(self, point, node_1, node_2, range_data):
        """
        p1과 p2를 잇는 선을 기준으로 x축은 +1, -1, y축은 +2, -2로 확장된 사각형 영역 내에
        좌표 point가 포함되는지 확인하는 함수.

        :param point: 확인할 좌표 (x, y)
        :param p1: 기준이 되는 첫 번째 점 (x1, y1)
        :param p2: 기준이 되는 두 번째 점 (x2, y2)
        :return: point가 확장된 영역 안에 있으면 True, 아니면 False
        """
        x_range_plus = range_data.get("x_range_plus", 1.0)
        y_range_plus = range_data.get("y_range_plus", 1.0)
        x_range_minus = range_data.get("x_range_minus", 1.0)
        y_range_minus = range_data.get("y_range_minus", 1.0)

        x1, y1 = node_1
        px, py = point
        if node_2 is None:
            x_min, x_max = x1 - x_range_minus, x1 + x_range_plus
            y_min, y_max = y1 - y_range_minus, y1 + y_range_plus
        else:
            x2, y2 = node_2
            x_min, x_max = min(x1, x2) - x_range_minus, max(x1, x2) + x_range_plus
            y_min, y_max = min(y1, y2) - y_range_minus, max(y1, y2) + y_range_plus

        # point가 확장된 범위 안에 있는지 확인
        return x_min <= px <= x_max and y_min <= py <= y_max

    # 현재 좌표와 가장 가까운 간선을 찾는 함수 (복귀 구역 찾기)
    def find_destination_closest_edge(self, x_axis, y_axis, angle, destination_waypoint):
        intersection_point = None
        closest_node = None
        closest_edge = None
        min_distance = float('inf')
        min_cost = float('inf')

        for now_node_name, edge_data in self.edges.items():
            for neighbor_node_name, cost in edge_data.items():
                now_node = self.nodes[now_node_name]
                neighbor_node = self.nodes[neighbor_node_name]

                # 두 노드에서 a까지의 거리 계산
                now_axis: tuple = (x_axis, y_axis)
                node_1: tuple = (now_node.x, now_node.y)
                node_2: tuple = (neighbor_node.x, neighbor_node.y)

                range_data = self.edge_range[now_node_name][neighbor_node_name]
                if range_data is not None and len(range_data) != 0:
                    if self.is_within_expanded_bounds(now_axis, node_1, node_2, range_data) is True:
                        dist_to_now = self.euclidean_distance(now_axis, node_1) + cost + angle_difference(angle, now_node.a)
                        dist_to_neighbor = self.euclidean_distance(now_axis, node_2) + cost + angle_difference(angle, neighbor_node.a)
                        clac_intersection_point = closer_axis_and_intersections(now_axis, node_1, node_2)

                        # 더 작은 거리 선택
                        if dist_to_now <= min_distance or dist_to_neighbor <= min_distance:
                            if dist_to_now < min_distance:
                                min_distance = dist_to_now
                            if dist_to_neighbor < min_distance:
                                min_distance = dist_to_neighbor

                            for node_name in [now_node_name, neighbor_node_name]:
                                path: list | None = self.lpa_star(None, node_name, destination_waypoint, False,False)
                                if path is not None:
                                    cost = self.get_path_cost(path, False)
                                    if cost < min_cost:
                                        min_cost = cost
                                        closest_node = node_name
                                        intersection_point = clac_intersection_point
                                        closest_edge = (now_node_name, neighbor_node_name)
                else:
                    continue
        return closest_node, intersection_point, closest_edge

    # 간선 근처에 있는 노드 찾기 (지나가는 구간에 겹치는 노드 찾기
    def find_edge_closest_nodes(self, nodes_1_name, nodes_2_name):
        closest_node = {}
        try:
            nodes_1 = self.nodes[nodes_1_name]
            nodes_2 = self.nodes[nodes_2_name]
            for now_node_name, node_data in self.nodes.items():
                if now_node_name != nodes_1_name and now_node_name != nodes_2_name:
                    range_data = {}
                    if nodes_1.x == nodes_2.x and nodes_1.x == nodes_2.y and nodes_1.a != nodes_2.a:
                        # 회전 포인트라면 범위 추가
                        range_data = {
                            "x_range_plus": 2.0,
                            "y_range_plus": 2.0,
                            "x_range_minus": 2.0,
                            "y_range_minus": 2.0
                        }
                    if self.is_within_expanded_bounds((node_data.x, node_data.y), (nodes_1.x, nodes_1.y), (nodes_2.x, nodes_2.y), range_data):
                        closest_node[now_node_name] = True
        except Exception:
            print(traceback.format_exc())
        return closest_node

    def visualize_graph(self):
        # g = nx.DiGraph()
        #
        # # Add edges
        # for from_node in self.edges:
        #     for to_node, weight in self.edges[from_node].items():
        #         g.add_edge(from_node, to_node, weight=weight)
        #
        # pos = nx.spring_layout(g)
        # plt.figure(figsize=(8, 6))
        #
        # # Draw nodes and edges
        # nx.draw(g, pos, with_labels=True, node_color='lightblue', node_size=1500, font_size=10)
        # edge_labels = nx.get_edge_attributes(g, 'weight')
        # nx.draw_networkx_edge_labels(g, pos, edge_labels=edge_labels)
        #
        # plt.show()
        fig, ax = plt.subplots()

        # 노드 그리기
        for node_name, node in self.nodes.items():
            ax.scatter(node.x, node.y, s=100, c='blue')  # 각 노드 좌표에 점을 그림
            ax.text(node.x, node.y, node_name, fontsize=12, ha='right')  # 노드 이름 표시

            # 각도에 따라 방향 화살표 그리기
            arrow_length = 0.5  # 화살표 길이
            arrow_dx = np.cos(np.radians(node.a)) * arrow_length
            arrow_dy = np.sin(np.radians(node.a)) * arrow_length
            ax.arrow(node.x, node.y, arrow_dx, arrow_dy, head_width=0.2, head_length=0.2, fc='green', ec='green')

        # 간선 그리기
        for from_node, neighbors in self.edges.items():
            from_node_obj = self.nodes[from_node]
            for to_node, properties in neighbors.items():
                to_node_obj = self.nodes[to_node]
                ax.plot([from_node_obj.x, to_node_obj.x], [from_node_obj.y, to_node_obj.y], 'k-', lw=2)  # 간선 그리기

        ax.set_title('Graph Visualization')
        plt.grid(True)
        plt.show()