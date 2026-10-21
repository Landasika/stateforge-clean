import sys
class TemplateEventResult(list):
    def __init__(self, items):
        list.__init__(self, items)

    def __unicode__(self):
        return u"".join(map(str, self))

    def __str__(self):
        if sys.version_info[0] >= 3:
            return self.__unicode__()
        return self.__unicode__().encode("utf-8")
