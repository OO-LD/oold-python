from pydantic.v1 import BaseModel as BaseModel_v1
from pydantic import BaseModel

from typing import TypeVar, Generic

T = TypeVar('T')  # Define type variable "T"

class GenericLinkedBaseModel(Generic[T]):

    def __init__(self, *a, **kw):
        # check if instance of pydantic.v1.BaseModel
        if issubclass(self.__class__, BaseModel_v1):
            print("Pydantic v1")
        # pprint(a)
        # pprint(kw)
        for name in list(kw):  # force copy of keys for inline-delete
            # rewrite <attr> to <attr>_iri
            # pprint(self.__fields__)
            extra = None
            if issubclass(self.__class__, BaseModel_v1):
                # pydantic v1
                if hasattr(self.__fields__[name].default, "json_schema_extra"):
                    extra = self.__fields__[name].default.json_schema_extra
            else:
                # pydantic v2
                extra = self.model_fields[name].json_schema_extra
            if "__iris__" not in kw:
                kw["__iris__"] = {}
            if extra and "range" in extra:
                arg_is_list = isinstance(kw[name], list)

                # annotation_is_list = False
                # args = self.model_fields[name].annotation.__args__
                # if hasattr(args[0], "_name"):
                #    is_list = args[0]._name == "List"
                if arg_is_list:
                    kw["__iris__"][name] = []
                    for e in kw[name][:]:  # interate over copy of list
                        if isinstance(e, BaseModel_v1) or isinstance(e, BaseModel):  # contructed with object ref
                            kw["__iris__"][name].append(e.id)
                        elif isinstance(e, str):  # constructed from json
                            kw["__iris__"][name].append(e)
                            kw[name].remove(e)  # remove to construct valid instance
                    if len(kw[name]) == 0:
                        if issubclass(self.__class__, BaseModel_v1):
                            kw[name] = None # else pydantic v1 will set a FieldInfo object
                        else: del kw[name]
                else:
                    if isinstance(kw[name], BaseModel_v1) or isinstance(kw[name], BaseModel):  # contructed with object ref
                        # print(kw[name].id)
                        kw["__iris__"][name] = kw[name].id
                    elif isinstance(kw[name], str):  # constructed from json
                        kw["__iris__"][name] = kw[name]
                        if issubclass(self.__class__, BaseModel_v1):
                            kw[name] = None # else pydantic v1 will set a FieldInfo object
                        else: del kw[name]

        
        if isinstance(self, BaseModel_v1):
            BaseModel_v1.__init__(self, *a, **kw)
        else: BaseModel.__init__(self, *a, **kw)
        #super(BaseModel, self).__init__(*a, **kw)

        self.__iris__ = kw["__iris__"]

    def __getattribute__(self, name):
        #print( "I am {0}".format(self.__orig_class__.__args__[0].__name__))
        # print("__getattribute__ ", name)
        # async? https://stackoverflow.com/questions/33128325/
        # how-to-set-class-attribute-with-await-in-init
        #if name in ["__dict__", "__pydantic_private__", "__iris__"]:
        #    return BaseModel.__getattribute__(self, name)  # prevent loop
        # if name in ["__pydantic_extra__"]
        print(name)
        if name in ["__dict__", "__pydantic_private__", "__iris__", "__post_root_validators__", "_get_pydantic_basemodel", "__class__"]:
            #if isinstance(self, BaseModel_v1):
            #    return BaseModel_v1.__getattribute__(self, name)
            #else: return BaseModel.__getattribute__(self, name)
            #return super().__getattribute__(name)
            return BaseModel.__getattribute__(self, name)
        else:
            #if hasattr(self, "__iris__"):
            if "__iris__" in self.__dict__:
                if name in self.__iris__:
                    if self.__dict__[name] is None or (
                        isinstance(self.__dict__[name], list)
                        and len(self.__dict__[name]) == 0
                    ):
                        iris = self.__iris__[name]
                        is_list = isinstance(iris, list)
                        if not is_list:
                            iris = [iris]

                        node_dict = self._resolve(iris)
                        if is_list:
                            node_list = []
                            for iri in iris:
                                node = node_dict[iri]
                                node_list.append(node)
                            self.__setattr__(name, node_list)
                        else:
                            node = node_dict[iris[0]]
                            if node:
                                self.__setattr__(name, node)

        #print(super())
        #if self._get_pydantic_basemodel() == BaseModel_v1:
        #    return BaseModel_v1.__getattribute__(self, name)
        #else: 
        #    return BaseModel.__getattribute__(self, name)
        #return BaseModel_v1.__getattribute__(self, name)
        if isinstance(self, BaseModel_v1):
            return BaseModel_v1.__getattribute__(self, name)
        else: return BaseModel.__getattribute__(self, name)
        #T.__getattribute__(self, name)

    def _object_to_iri(self, d):
        for name in list(d):  # force copy of keys for inline-delete
            if name in self.__iris__:
                d[name] = self.__iris__[name]
                # del d[name + "_iri"]
        return d

    def dict(self, **kwargs):  # extent BaseClass export function
        print("dict")
        d = super().dict(**kwargs)
        # pprint(d)
        self._object_to_iri(d)
        # pprint(d)
        return d



