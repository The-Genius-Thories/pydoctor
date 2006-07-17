from pydoctor import model, ast_pp, astbuilder
from compiler import ast

class TwistedClass(model.Class):
    isinterface = False
    implementsOnly = False
    implementedby_directly = None # [objects], when isinterface == True
    implementedby_indirectly = None # [objects], when isinterface == True
    def setup(self):
        super(TwistedClass, self).setup()
        self.implements_directly = [] # [name of interface]
        self.implements_indirectly = [] # [(interface name, directly implemented)]

class Attribute(model.Documentable):
    kind = "Attribute"
    pass

def addInterfaceInfoToClass(cls, interfaceargs, implementsOnly):
    cls.implementsOnly = implementsOnly
    if implementsOnly:
        cls.implements_directly = []
    for arg in interfaceargs:
        cls.implements_directly.append(
            cls.dottedNameToFullName(ast_pp.pp(arg)))

    

class TwistedModuleVisitor(astbuilder.ModuleVistor):
    def funcNameFromCall(self, node):
        str_base = ast_pp.pp(node.node)
        return self.builder.current.dottedNameToFullName(str_base)

    def visitAssign(self, node):
        # i would like pattern matching in python please
        # if match(Assign([AssName(?name, _)], CallFunc(?funcName, [Const(?docstring)])), node):
        #     ...
        if len(node.nodes) != 1 or \
               not isinstance(node.nodes[0], ast.AssName) or \
               not isinstance(self.builder.current, model.Class) or \
               not isinstance(node.expr, ast.CallFunc) or \
               self.funcNameFromCall(node.expr) != 'zope.interface.Attribute':
            self.default(node)
            return
        args = node.expr.args
        if len(args) != 1 or \
               not isinstance(args[0], ast.Const) or \
               not isinstance(args[0].value, str):
            self.default(node)
            return
        attr = self.builder._push(Attribute, node.nodes[0].name, args[0].value)
        attr.linenumber = node.lineno
        self.builder._pop(Attribute)
        
    def visitCallFunc(self, node):
        base = self.funcNameFromCall(node)
        meth = getattr(self, "visitCallFunc_" + base.replace('.', '_'), None)
        if meth is not None:
            meth(base, node)

    def visitCallFunc_zope_interface_implements(self, funcName, node):
        if not isinstance(self.builder.current, model.Class):
            self.default(node)
            return
        addInterfaceInfoToClass(self.builder.current, node.args,
                                funcName == 'zope.interface.implementsOnly')
    visitCallFunc_zope_interface_implementsOnly = visitCallFunc_zope_interface_implements
        
    def visitCallFunc_zope_interface_classImplements(self, funcName, node):
        clsname = self.builder.current.dottedNameToFullName(ast_pp.pp(node.args[0]))
        if clsname not in self.system.allobjects:
            self.builder.warning("classImplements on unknown class", clsname)
            return
        cls = self.system.allobjects[clsname]
        addInterfaceInfoToClass(cls, node.args[1:],
                                funcName == 'zope.interface.classImplementsOnly')
    visitCallFunc_zope_interface_classImplementsOnly = visitCallFunc_zope_interface_classImplements
    
    def visitCallFunc_twisted_python_util_moduleMovedForSplit(self, funcName, node):
        # XXX this is rather fragile...
        origModuleName, newModuleName, moduleDesc, \
                        projectName, projectURL, globDict = node.args
        moduleDesc = ast_pp.pp(moduleDesc)[1:-1]
        projectName = ast_pp.pp(projectName)[1:-1]
        projectURL = ast_pp.pp(projectURL)[1:-1]
        modoc = """
%(moduleDesc)s

This module is DEPRECATED. It has been split off into a third party
package, Twisted %(projectName)s. Please see %(projectURL)s.

This is just a place-holder that imports from the third-party %(projectName)s
package for backwards compatibility. To use it, you need to install
that package.
""" % {'moduleDesc': moduleDesc,
       'projectName': projectName,
       'projectURL': projectURL}
        self.builder.current.docstring = modoc
        
        


class TwistedASTBuilder(astbuilder.ASTBuilder):
    Class = TwistedClass
    ModuleVistor = TwistedModuleVisitor

    def _finalStateComputations(self):
        tpc = 'twisted.python.components'
        if tpc in self.system.allobjects:
            self.push(self.system.allobjects[tpc])
            self.pushClass('Interface', None)
            self.popClass()
            self.pop(self.system.allobjects[tpc])
        super(TwistedASTBuilder, self)._finalStateComputations()

        if tpc in self.system.allobjects:
            self.markInterface(self.system.allobjects[tpc+'.Interface'])
        for cls in self.system.objectsOfType(model.Class):
            if 'zope.interface.Interface' in cls.bases:
                self.markInterface(cls)

        for cls in self.system.objectsOfType(model.Class):
            if cls.isinterface or len(cls.baseobjects) != cls.baseobjects.count(None):
                continue
            self.push_implements_info(cls, cls.implements_directly)

        for cls in self.system.objectsOfType(model.Class):
            for interface in cls.implements_directly:
                if interface in self.system.allobjects and '.test.' not in interface:
                    interface_ob = self.system.allobjects[interface]
                    if interface_ob.implementedby_directly is None:
                        self.warning("probable interface not marked as such",
                                     interface_ob.fullName())
                        interface_ob.implementedby_directly = []
                        interface_ob.implementedby_indirectly = []
                    interface_ob.implementedby_directly.append(cls.fullName())
            for interface in cls.implements_indirectly:
                if interface in self.system.allobjects and '.test.' not in interface:
                    interface_ob = self.system.allobjects[interface]
                    if interface_ob.implementedby_indirectly is None:
                        self.warning("probable interface not marked as such",
                                     interface_ob.fullName())
                        interface_ob.implementedby_directly = []
                        interface_ob.implementedby_indirectly = []
                    interface_ob.implementedby_indirectly.append(cls.fullName())


    def markInterface(self, cls):
        cls.isinterface = True
        cls.kind = "Interface"
        cls.implementedby_directly = []
        cls.implementedby_indirectly = []
        for sc in cls.subclasses:
            if '.test.' not in sc.fullName():
                self.markInterface(sc)

    def push_implements_info(self, cls, interfaces):
        for ob in cls.subclasses:
            for interface in interfaces:
                if interface not in ob.implements_indirectly:
                    ob.implements_indirectly.append(interface)
            if ob.implementsOnly:
                ob.implements_indirectly = []
                newinterfaces = ob.implements_directly
            else:
                newinterfaces = interfaces + ob.implements_directly
            self.push_implements_info(ob, newinterfaces)