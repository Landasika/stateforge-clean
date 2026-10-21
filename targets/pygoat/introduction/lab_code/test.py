import subprocess
import yaml
stream = open('/home/fox/test.yaml', 'r')
data = yaml.load(stream)
print(data + "\n")
