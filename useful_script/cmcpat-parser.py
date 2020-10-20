#!/usr/bin/python
from optparse import OptionParser
import sys
import re
import json
import types
import math
import copy
from xml.etree import ElementTree as ET
from xml.dom import minidom # saurav版添加
# source from https://github.com/kingmouf/cmcpat/blob/master/Scripts/GEM5ToMcPAT.py
# 使用方法: ./cmcpat-parser.py stats.txt config.json template.xml

def prettify(elem): # saurav版添加
    """Return a pretty-printed XML string for the Element.
    """
    rough_string = ET.tostring(elem, 'utf-8')
    reparsed = minidom.parseString(rough_string)
    return reparsed.toprettyxml(indent="  ")

class PIParser(ET.XMLTreeBuilder):
   def __init__(self):
       ET.XMLTreeBuilder.__init__(self)
       # assumes ElementTree 1.2.X
       self._parser.CommentHandler = self.handle_comment
       self._parser.ProcessingInstructionHandler = self.handle_pi
       self._target.start("document", {}) #xml文件的处理

   def close(self):
       self._target.end("document")
       return ET.XMLTreeBuilder.close(self)

   def handle_comment(self, data):
       self._target.start(ET.Comment, {})
       self._target.data(data)
       self._target.end(ET.Comment)

   def handle_pi(self, target, data):
       self._target.start(ET.PI, {})
       self._target.data(target + " " + data)
       self._target.end(ET.PI)

def parse(source):
    return ET.parse(source, PIParser())
# 设置输入格式以及调用流

def main():
    global opts # OptionParser
    usage = "usage: %prog [options] <gem5 stats file> <gem5 config file (json)> <mcpat template file>" #备注
    parser = OptionParser(usage=usage)
    parser.add_option("-q", "--quiet", 
        action="store_false", dest="verbose", default=True,
        help="don't print status messages to stdout")
    parser.add_option("-o", "--out", type="string",
        action="store", dest="out", default="mcpat-out.xml",
        help="output file (input to McPAT)")
    (opts, args) = parser.parse_args()
    if len(args) != 3:
        parser.print_help()
        sys.exit(1)
    readStatsFile(args[0]) # 读取文件
    readConfigFile(args[1])
    readMcpatFile(args[2])
    prepareTemplate(opts.out) # 来自saurav版本
    dumpMcpatOut(opts.out) # 输出文件数据

def dumpMcpatOut(outFile):
    # 抓取根节点元素，对模板文件
    rootElem = templateMcpat.getroot()
    configMatch = re.compile(r'config\.([a-zA-Z0-9_:\.]+)')
    #replace params with values from the GEM5 config file 
    #for param in rootElem.iter('param'):
    # 提取便签和值
    for param in rootElem.getiterator('param'):
        name = param.attrib['name']  # 打印表格中的name
        value = param.attrib['value'] # 打印表格中的value
        if 'config' in value:
            allConfs = configMatch.findall(value)
            for conf in allConfs:
                confValue = getConfValue(conf)
         
#Be careful because in some cases, GEM5 seems to post a single value but inside [...]
#python seems to think this is a list and creates problems         
         
                if isinstance(confValue, types.ListType):
                    if (len(confValue)==1):
                        confValue=confValue[0]
     
                    
                value = re.sub("config."+ conf, str(confValue), value)
            if "," in value: #value中的格式处理
                exprs = re.split(',', value)
                for i in range(len(exprs)):
                    exprs[i] = str(eval(exprs[i]))
                param.attrib['value'] = ','.join(exprs)
            else:
                param.attrib['value'] = str(eval(str(value)))

    #replace stats with values from the GEM5 stats file 
    statRe = re.compile(r'stats\.([a-zA-Z0-9_:\.]+)')
    #for stat in rootElem.iter('stat'):
    for stat in rootElem.getiterator('stat'):
        name = stat.attrib['name']
        value = stat.attrib['value']
        if 'stats' in value:
            allStats = statRe.findall(value)
            expr = value
            for i in range(len(allStats)):
                if allStats[i] in stats:
                    expr = re.sub('stats.%s' % allStats[i], stats[allStats[i]], expr,1) #处理?
                else:
                    print "***WARNING: %s does not exist in stats***" % allStats[i]
                    print "\t Please use the right stats in your McPAT template file"

            if 'config' not in expr and 'stats' not in expr:
                stat.attrib['value'] = str(eval(expr))
    #Write out the xml file 写输出文件
    if opts.verbose: print "Writing input to McPAT in: %s" % outFile 
    templateMcpat.write(outFile)

def getConfValue(confStr): # 读取配置的值
    spltConf = re.split('\.', confStr) 
    currConf = config
    currHierarchy = ""
    for x in spltConf:
        currHierarchy += x
        if x not in currConf:
            if isinstance(currConf, types.ListType):
                #this is mostly for system.cpu* as system.cpu is an array
                #This could be made better
                if x not in currConf[0]:
                    print "%s does not exist in config" % currHierarchy 
                else:
                    currConf = currConf[0][x]
            else:
                    print "***WARNING: %s does not exist in config.***" % currHierarchy 
                    print "\t Please use the right config param in your McPAT template file"
        else:
            currConf = currConf[x]
        currHierarchy += "."
    return currConf
    

def readStatsFile(statsFile):
    global stats
    stats = {}
    if opts.verbose: print "Reading GEM5 stats from: %s" %  statsFile
    F = open(statsFile)
    ignores = re.compile(r'^---|^$')
    #Please note that changes in the gem5 stats file may require changes here. 也就是gem5数据文件的更新需要在此改动
    #Note for last stable version of gem5: Some statistics names are appended by numbers similar to this: 5e+10-1e+11 .
    statLine = re.compile(r'([a-zA-Z0-9_\.:+-]+)\s+([-+]?[0-9]+\.[0-9]+|[-+]?[0-9]+|nan|inf)')
    count = 0 
    for line in F:
        #ignore empty lines and lines starting with "---"  
        if not ignores.match(line):
            count += 1
	    #Exceptions are used to make sure that updates to gem5 stats file do not break the 
	    #converter.
	    try:
            	statKind = statLine.match(line).group(1) #stats的第一列
            	statValue = statLine.match(line).group(2)
	    except Exception as e:
	    	continue
            if statValue == 'nan': # NAN数据改为0
                print "\tWarning (stats): %s is nan. Setting it to 0" % statKind
                statValue = '0'
            if statKind == 'testsys.cpu.num_idle_cycles':
                stats[statKind] = str(int(float(statValue) + 0.5)) # 新版本的输出并没有testsys.cpu.num_idle_cycles
	    else:
		if statKind == 'testsys.cpu.num_busy_cycles':
			stats[statKind] = str(int(float(statValue) + 0.5))
		else:
			stats[statKind] = statValue
            		
    F.close()

def readConfigFile(configFile):
    global config
    if opts.verbose: print "Reading config from: %s" % configFile
    F = open(configFile)
    config = json.load(F) # 对config.json的加载,没有处理
    
    F.close()

def readMcpatFile(templateFile):
    global templateMcpat 
    if opts.verbose: print "Reading McPAT template from: %s" % templateFile 
    templateMcpat = parse(templateFile) # 加载模板以及转化
   
# 以下片段来自 saurav, 
def prepareTemplate(outFile):
    numCores = len(config["system"]["cpu"]) #对L2的处理: 私有还是共享
    privateL2 = config["system"]["cpu"][0].has_key('l2cache')
    sharedL2 = config["system"].has_key('l2')
    if privateL2:
        numL2 = numCores
    elif sharedL2:
        numL2 = 1
    else:
        numL2 = 0
    elemCounter = 0
    root = templateMcpat.getroot() #根据配置改动模板中的参数
    for child in root[0][0]:
        elemCounter += 1 # to add elements in correct sequence

        if child.attrib.get("name") == "number_of_cores":
            child.attrib['value'] = str(numCores)
        if child.attrib.get("name") == "number_of_L2s":
            child.attrib['value'] = str(numL2)
        if child.attrib.get("name") == "Private_L2":
            if sharedL2:
                Private_L2 = str(0)
            else:
                Private_L2 = str(1)
            child.attrib['value'] = Private_L2
        temp = child.attrib.get('value')

        # to consider all the cpus in total cycle calculation
        if isinstance(temp, basestring) and "cpu." in temp and temp.split('.')[0] == "stats":
            value = "(" + temp.replace("cpu.", "cpu0.") + ")"
            for i in range(1, numCores):
                value = value + " + (" + temp.replace("cpu.", "cpu"+str(i)+".") +")"
            child.attrib['value'] = value

        # remove a core template element and replace it with number of cores template elements 对core替换
        if child.attrib.get("name") == "core": # 多core,复制core的属性
            coreElem = copy.deepcopy(child)
            coreElemCopy = copy.deepcopy(coreElem)
            for coreCounter in range(numCores):
                coreElem.attrib["name"] = "core" + str(coreCounter) # core编号
                coreElem.attrib["id"] = "system.core" + str(coreCounter)
                for coreChild in coreElem:
                    childId = coreChild.attrib.get("id")
                    childValue = coreChild.attrib.get("value")
                    childName = coreChild.attrib.get("name")
                    if isinstance(childName, basestring) and childName == "x86": # 改动ISA的值,应该还需要ARM的版本
                        if config["system"]["cpu"][coreCounter]["isa"][0]["type"] == "X86ISA":
                            childValue = "1"
                        else:
                            childValue = "0"
                    if isinstance(childId, basestring) and "core" in childId:
                        childId = childId.replace("core", "core" + str(coreCounter)) #core替换为core_n
                    if isinstance(childValue, basestring) and "cpu." in childValue and "stats" in childValue.split('.')[0]:
                        childValue = childValue.replace("cpu." , "cpu" + str(coreCounter)+ ".")
                    if isinstance(childValue, basestring) and "cpu." in childValue and "config" in childValue.split('.')[0]:
                        childValue = childValue.replace("cpu." , "cpu." + str(coreCounter)+ ".")
                    if len(list(coreChild)) is not 0:
                        for level2Child in coreChild:
                            level2ChildValue = level2Child.attrib.get("value")
                            if isinstance(level2ChildValue, basestring) and "cpu." in level2ChildValue and "stats" in level2ChildValue.split('.')[0]:
                                level2ChildValue = level2ChildValue.replace("cpu." , "cpu" + str(coreCounter)+ ".")
                            if isinstance(level2ChildValue, basestring) and "cpu." in level2ChildValue and "config" in level2ChildValue.split('.')[0]:
                                level2ChildValue = level2ChildValue.replace("cpu." , "cpu." + str(coreCounter)+ ".")
                            level2Child.attrib["value"] = level2ChildValue
                    if isinstance(childId, basestring):
                        coreChild.attrib["id"] = childId
                    if isinstance(childValue, basestring):
                        coreChild.attrib["value"] = childValue
                root[0][0].insert(elemCounter, coreElem)
                coreElem = copy.deepcopy(coreElemCopy)
                elemCounter += 1
            root[0][0].remove(child)
            elemCounter -= 1

        # # remove a L2 template element and replace it with the private L2 template elements
        # if child.attrib.get("name") == "L2.shared":
        #     print child
        #     if sharedL2:
        #         child.attrib["name"] = "L20"
        #         child.attrib["id"] = "system.L20"
        #     else:
        #         root[0][0].remove(child)

        # remove a L2 template element and replace it with number of L2 template elements 对L2进行替换
        if child.attrib.get("name") == "L2":
            if privateL2:
                l2Elem = copy.deepcopy(child)
                l2ElemCopy = copy.deepcopy(l2Elem)
                for l2Counter in range(numL2):
                    l2Elem.attrib["name"] = "L2" + str(l2Counter)
                    l2Elem.attrib["id"] = "system.L2" + str(l2Counter)
                    for l2Child in l2Elem:
                        childValue = l2Child.attrib.get("value")
                        if isinstance(childValue, basestring) and "cpu." in childValue and "stats" in childValue.split('.')[0]:
                            childValue = childValue.replace("cpu." , "cpu" + str(l2Counter)+ ".")
                        if isinstance(childValue, basestring) and "cpu." in childValue and "config" in childValue.split('.')[0]:
                            childValue = childValue.replace("cpu." , "cpu." + str(l2Counter)+ ".")
                        if isinstance(childValue, basestring):
                            l2Child.attrib["value"] = childValue
                    root[0][0].insert(elemCounter, l2Elem)
                    l2Elem = copy.deepcopy(l2ElemCopy)
                    elemCounter += 1
                root[0][0].remove(child)
            else:
                child.attrib["name"] = "L20"
                child.attrib["id"] = "system.L20"
                for l2Child in child:
                    childValue = l2Child.attrib.get("value")
                    if isinstance(childValue, basestring) and "cpu.l2cache." in childValue:
                        childValue = childValue.replace("cpu.l2cache." , "l2.")

    prettify(root)
    #templateMcpat.write(outputFile)   
    

if __name__ == '__main__':
    main()
