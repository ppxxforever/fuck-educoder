# -*- coding: UTF-8 -*-
import math
import operator
from functools import reduce
import os
from shutil import copy
import json

def analyze_json(json_file):
    uml_file = open(json_file, "r")
    uml_json = json.load(uml_file)
    owned_elements = uml_json.get('ownedElements')

    if len(owned_elements) == 1:
        element_list = owned_elements[0]['ownedElements'][1]['ownedElements'][0]['participants']
        element_list2 = owned_elements[0]['ownedElements'][1]['ownedElements'][0]['ownedElements']
        element_list3 = owned_elements[0]['ownedElements'][1]['ownedElements'][0]['messages']
    else:
        element_list = owned_elements[1]['ownedElements'][0]['participants']
        element_list2 = owned_elements[1]['ownedElements'][0]['ownedElements']
        element_list3 = owned_elements[1]['ownedElements'][0]['messages']


    

    judge_customer_entity0 = analyze_element(element_list, '酒店工作人员', 'UMLLifeline')
    judge_customer_entity1 = analyze_element(element_list, '注册页面', 'UMLLifeline')
    judge_customer_entity2 = analyze_element(element_list, '房间库', 'UMLLifeline')
    judge_customer_entity3 = analyze_element(element_list2, 'SequenceDiagram1', 'UMLSequenceDiagram')
    # judge_customer_entity4 = analyze_element(element_list3, '选择修改条目', 'UMLMessage')

    source_id = get_id(element_list, '酒店工作人员', 'UMLLifeline')
    target_id = get_id(element_list, '注册页面', 'UMLLifeline')

    judge_customer_entity4 = analyze_line1(element_list3, '选择修改条目', 'UMLMessage', source_id, target_id)



    output(judge_customer_entity0, "酒店工作人员生命线")
    output(judge_customer_entity1, "注册页面生命线")
    output(judge_customer_entity2, "房间库生命线")
    output(judge_customer_entity3, "顺序图建立")
    output(judge_customer_entity4, "消息传递")
    
        

def output(judge, value):
    if judge:
        print(value)
    else:
        print(value + "出错或缺失，请重新检查")
        return 0   

def analyze_element(element_list, name, type):
    for element in element_list:
        if element.get('name') == name and element.get('_type') == type:
            return 1
    return 0

def analyze_line(element_list, name, type, visibility, types):
    for element in element_list:
        if element.get('name') == name and element.get('_type') == types and element.get('visibility') == visibility and element.get('type') == type :
            return 1
    return 0
def analyze_line1(element_list, name, type, sourceId, targetId):
    for element in element_list:
        if element.get('name') == name and element['_type'] == type and element["source"]["$ref"] == sourceId and element["target"]["$ref"] == targetId :
           return 1
    return 0    

def get_id(element_list, name, type):
    for element in element_list:
        if element.get('name') == name and element.get('_type') == type:
            return element.get('_id')
    return " "

def detect_dirc(path, file):
    if os.path.exists(path) and os.listdir(path):
        scores = {}
        json_file = os.path.join(path + file)
        score = analyze_json(json_file)
        scores[file] = score
        return scores
    raise ValueError('答案不存在，请上传答案')

if __name__ == '__main__':
    if os.path.exists('/data/workspace/myshixun/submit/submit_step4/s'):
        os.remove('/data/workspace/myshixun/submit/submit_step4/s')
    file_path = '/data/workspace/myshixun/submit/submit_step4/'
    #   file_path = 'C:\\Users\\li zhenghui\\Desktop\\结构化设计\\数据流图-详细步骤\\submit'
    pathDir = os.listdir(file_path)
    to_path = '/data/workspace/myshixun/Answer/answer4'
    #   to_path = 'C:\\Users\\li zhenghui\\Desktop\\结构化设计\\数据流图-详细步骤\\submit_copy'
    for one in pathDir:
        from_path = os.path.join(file_path,one)
        copy(from_path,to_path)
    file = "step4.mdj"
    scores = detect_dirc(file_path, file)
