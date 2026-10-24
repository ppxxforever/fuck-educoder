# -*- coding: UTF-8 -*-
import operator
from functools import reduce
import os
from shutil import copy
import json

def analyze_json(json_file):
  try:
    uml_file = open(json_file, "r")
    uml_json = json.load(uml_file)

    # 获取Json中我们所需的元素，不同图的元素路径可能不同
    # print(uml_json)
    owned_elements = uml_json.get('ownedElements')
    # 首先获取当前流程图的所有信息
    fcflowchart_list = owned_elements[1]['ownedElements']
    
    
    
    
    # 依次判断各处理是否存在
    judge_odddisplay_process = analyze_element(fcflowchart_list, '商品展示', 'FCProcess')
    judge_oddbuy_process = analyze_element(fcflowchart_list, '商品订购', 'FCProcess')
    judge_order_process = analyze_element(fcflowchart_list, '销售订单管理', 'FCProcess')

    # 依次判断数据库是否存在
    judge_goodsdatabase = analyze_database(fcflowchart_list, '商品信息数据库', 'FCDatabase')
    judge_usersdatabase = analyze_database(fcflowchart_list, '客户信息数据库', 'FCDatabase')

    # 依次判断文件系统是否存在
    judge_filesys = analyze_filesys(fcflowchart_list, '订单信息存储', 'FCDirectAccessStorage')

    # 依次判断信息表单是否存在
    judge_goodsorder = analyze_order(fcflowchart_list, '商品信息表单', 'FCStoredData')
    judge_usersorder = analyze_order(fcflowchart_list, '客户信息表单', 'FCStoredData')

    # 依次判断文件表单是否存在
    judge_buysorder = analyze_files(fcflowchart_list, '销售订单', 'FCDocument')
   



    # 获取所有的数据流信息
    # lines_list = fcflowchart_list[2]['ownedElements']

    
    # 依次判断各连线是否存在
    # source_id:连线起始元素id
    # target_id:连线终止元素id
    odddisplay_process_id = get_id(fcflowchart_list, '商品展示', 'FCProcess')
    
    oddbuy_process_id = get_id(fcflowchart_list, '商品订购', 'FCProcess')
    order_process_id = get_id(fcflowchart_list, '销售订单管理', 'FCProcess')
    
    odddisplay_goodsdatabase_id = get_id(fcflowchart_list, '商品信息数据库', 'FCDatabase')
    odddisplay_usersdatabase_id = get_id(fcflowchart_list, '客户信息数据库', 'FCDatabase')

    odddisplay_goodsorder_id = get_id(fcflowchart_list, '商品信息表单', 'FCStoredData')
    odddisplay_usersoder_id = get_id(fcflowchart_list, '客户信息表单', 'FCStoredData')

    odddisplay_filesys_id = get_id(fcflowchart_list, '订单信息存储', 'FCDirectAccessStorage')

    odddisplay_files_id = get_id(fcflowchart_list, '销售订单', 'FCDocument')

    # 如果有一个元素没找到，就不再判断连线
    if odddisplay_process_id == 0 or oddbuy_process_id == 0 or order_process_id == 0 or odddisplay_goodsdatabase_id == 0 or odddisplay_usersdatabase_id == 0 or odddisplay_goodsorder_id == 0 or odddisplay_usersoder_id == 0 or odddisplay_filesys_id == 0 or odddisplay_files_id == 0:
        print("缺少元素，请检查答案")
        # raise ValueError("缺少元素，请检查答案")

    
    judge_FCFlow_1 = analyze_line(fcflowchart_list, odddisplay_goodsdatabase_id, odddisplay_goodsorder_id, 'FCFlow')
    judge_FCFlow_2 = analyze_line(fcflowchart_list, odddisplay_goodsorder_id, odddisplay_process_id, 'FCFlow')
    judge_FCFlow_3 = analyze_line(fcflowchart_list, odddisplay_goodsorder_id, oddbuy_process_id, 'FCFlow')
    judge_FCFlow_4 = analyze_line(fcflowchart_list, odddisplay_usersdatabase_id, odddisplay_usersoder_id, 'FCFlow')
    judge_FCFlow_5 = analyze_line(fcflowchart_list, odddisplay_usersoder_id, oddbuy_process_id, 'FCFlow')
    judge_FCFlow_6 = analyze_line(fcflowchart_list, oddbuy_process_id, order_process_id, 'FCFlow')
    judge_FCFlow_7 = analyze_line(fcflowchart_list, order_process_id, odddisplay_files_id, 'FCFlow')
    judge_FCFlow_8 = analyze_line(fcflowchart_list, odddisplay_files_id, odddisplay_filesys_id, 'FCFlow')

    # 先检查各个形式化符号是否存在
    output(judge_odddisplay_process, "商品展示处理 元素")
    output(judge_oddbuy_process, "商品订购处理 元素")
    output(judge_order_process, "销售订单管理处理 元素")

    output(judge_goodsdatabase, "商品信息数据库 元素")
    output(judge_usersdatabase, "客户信息数据库 元素")

    output(judge_filesys, "订单信息存储 元素")

    output(judge_goodsorder, "商品信息表单 元素")
    output(judge_usersorder, "客户信息表单 元素")

    output(judge_buysorder, "销售订单 元素")

    

    # 依次判断连线是否正确
    output(judge_FCFlow_1, '商品信息数据库 --> 商品信息表单 数据流')
    output(judge_FCFlow_2, '商品信息表单 --> 商品展示 数据流')
    output(judge_FCFlow_3, '商品信息表单 --> 商品订购 数据流')
    output(judge_FCFlow_4, '客户信息数据库 --> 客户信息表单 数据流')
    output(judge_FCFlow_5, '客户信息表单 --> 商品订购 数据流')
    output(judge_FCFlow_6, '商品订购 --> 销售订单管理 数据流')
    output(judge_FCFlow_7, '销售订单管理 --> 销售订单 数据流')
    output(judge_FCFlow_8, '销售订单 --> 订单信息存储 数据流')

    '''
    # 依次输出图中各元素。若元素绘制正确，则输出内容与标准答案一致；若绘制错误，则会输出“该元素出错”
    output(judge_customer_entity, "顾客实体")
    output(judge_admin_entity, "管理员实体")
    output(judge_process, "网上商城系统")
    output(judge_DFDFlow_1, "在线注册数据流")
    output(judge_DFDFlow_2, "购物数据流")
    output(judge_DFDFlow_3, "提交订单数据流")
    output(judge_DFDFlow_4, "付款数据流")
    '''

  except:
    print("答案没有内容，请按照要求作答")

# 检查实体
def analyze_element(element_list, name, types):
    for element in element_list:
        if element.get('name') == name and element.get('_type') == types:
            return 1
    return 0

# 检查数据库
def analyze_database(element_list, name, types):
    for element in element_list:
        if element.get('name') == name and element.get('_type') == types:
            return 1
    return 0

# 检查文件系统
def analyze_filesys(element_list, name, types):
    for element in element_list:
        if element.get('name') == name and element.get('_type') == types:
            return 1
    return 0

# 检查表单
def analyze_order(element_list, name, types):
    for element in element_list:
        if element.get('name') == name and element.get('_type') == types:
            return 1
    return 0

# 检查文件
def analyze_files(element_list, name, types):
    for element in element_list:
        if element.get('name') == name and element.get('_type') == types:
            return 1
    return 0

# 检查连线
def analyze_line(element_list, source, target, f_type):
    for element in element_list:
        if element.get('_id') == source:
            if(element.get("ownedElements") == None):
                return 0
            else:
                oe_list = element.get("ownedElements")
                for item in oe_list:
                    if item['_type'] == f_type and item["target"]["$ref"] == target:
                        return 1
    return 0

def get_id(element_list, name, type):
    for element in element_list:
        if element.get('name') == name and element.get('_type') == type:
            return element.get('_id')
    print('无法找到 ' + name + ' 元素')
    return 0

def detect_dirc(path, file):
  if os.path.exists(path) and os.listdir(path):
    json_file = os.path.join(path + file)
    analyze_json(json_file)
    return
  raise ValueError('答案不存在，请上传答案')

def output(judge, value):
    if judge: 
        # print(value + " 元素正确(√)")
        pass
    else:
        print(value + " 出错，请重新检查(×)")

if __name__ == '__main__':
  file_path = '/data/workspace/myshixun/系统流程图/submit/'
  path_dir = os.listdir(file_path)
  to_path = '/data/workspace/myshixun/系统流程图/submit_copy/'
  
  for one in path_dir:
    from_path = os.path.join(file_path,one)
    # copy(from_path,to_path)
  
  file = "step2.mdj"
  detect_dirc(file_path, file)
