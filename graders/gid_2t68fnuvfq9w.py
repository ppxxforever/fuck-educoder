 # -*- coding: UTF-8 -*-
import operator
from functools import reduce
import os
from shutil import copy
import json
import logging

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
    judge_userlogin_process = analyze_element(fcflowchart_list, '客户登录', 'FCProcess')

    # 依次判断数据库是否存在
    judge_usersdatabase = analyze_database(fcflowchart_list, '客户数据库', 'FCDatabase')

    # 依次判断信息表单是否存在
    judge_usersorder = analyze_order(fcflowchart_list, '客户表单信息', 'FCStoredData')



    
    # 依次判断各连线是否存在
    # source_id:连线起始元素id
    # target_id:连线终止元素id
    userlogin_process_id = get_id(fcflowchart_list, '客户登录', 'FCProcess')
    
    odddisplay_usersdatabase_id = get_id(fcflowchart_list, '客户数据库', 'FCDatabase')

    odddisplay_usersoder_id = get_id(fcflowchart_list, '客户表单信息', 'FCStoredData')


    # 如果有一个元素没找到，就不再判断连线
    if userlogin_process_id == 0 or odddisplay_usersdatabase_id == 0 or odddisplay_usersoder_id == 0:
        print("缺少符号元素，请检查答案")
        # raise ValueError("缺少符号元素，请检查答案")

    # 获取所有的数据流信息
    # lines_list = fcflowchart_list[2]['ownedElements']
    judge_FCFlow_1 = analyze_line(fcflowchart_list, odddisplay_usersdatabase_id, odddisplay_usersoder_id, 'FCFlow')
    judge_FCFlow_2 = analyze_line(fcflowchart_list, odddisplay_usersoder_id, userlogin_process_id, 'FCFlow')
  

    # 先检查各个形式化符号是否存在
    output(judge_userlogin_process, "客户登录 元素")

    output(judge_usersdatabase, "客户数据库 元素")

    output(judge_usersorder, "客户表单信息 元素")


    

    # 依次判断连线是否正确
    output(judge_FCFlow_1, '客户数据库 --> 客户表单信息 数据流')
    output(judge_FCFlow_2, '客户表单信息 --> 客户登录 数据流')
 

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
  if os.path.exists(os.path.join(path, file)) and os.listdir(path):
    json_file = os.path.join(path + file)
    analyze_json(json_file)
    return
  #raise ValueError('答案不存在，请上传答案')
  print('答案不存在，请上传答案')

def output(judge, value):
    if judge: 
        logging.info(value + " 元素正确(√)")
        pass
    else:
        print(value + " 出错，请重新检查(×)")

if __name__ == '__main__':
  file_path = '/data/workspace/myshixun/系统流程图/submit_step_2/'
  path_dir = os.listdir(file_path)
  to_path = '/data/workspace/myshixun/系统流程图/submit_copy/'
  
  for one in path_dir:
    from_path = os.path.join(file_path,one)
    # copy(from_path,to_path)
  
  file = "step.mdj"
  detect_dirc(file_path, file)
