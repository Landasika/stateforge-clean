from abc import ABC, abstractproperty
from enum import Enum
import attr
__all__ = (
    "NavigationContentType",
    "NavigationLink",
    "NavigationExternalLink",
    "NavigationHeader",
    "NavigationDivider",
)


class NavigationContentType(Enum):
    

    link = 0
    external_link = 1
    header = 2
    divider = 3


class NavigationItem(ABC):
    content_type = abstractproperty(lambda: None)


@attr.s(eq=True, order=True, hash=True, repr=True, frozen=True, slots=True)
class NavigationLink(NavigationItem):
    

    endpoint = attr.ib()
    name = attr.ib()
    icon = attr.ib(default="")
    active = attr.ib(default=False)
    urlforkwargs = attr.ib(factory=dict)
    content_type = NavigationContentType.link


@attr.s(eq=True, order=True, hash=True, repr=True, frozen=True, slots=True)
class NavigationExternalLink(NavigationItem):
    
    uri = attr.ib()
    name = attr.ib()
    icon = attr.ib(default="")
    content_type = NavigationContentType.external_link
@attr.s(eq=True, order=True, hash=True, repr=True, frozen=True, slots=True)
class NavigationHeader(NavigationItem):
    text = attr.ib()
    icon = attr.ib(default="")
    content_type = NavigationContentType.header


@attr.s(eq=True, order=True, hash=True, repr=True, frozen=True, slots=True)
class NavigationDivider(NavigationItem):
    

    content_type = NavigationContentType.divider
