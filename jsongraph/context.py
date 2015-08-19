from rdflib import Graph, URIRef, RDF

from jsongraph.vocab import BNode
from jsongraph.query import Query, QueryNode
from jsongraph.provenance import Provenance
from jsongraph.common import GraphOperations


class Context(GraphOperations):

    def __init__(self, parent, identifier=None, prov=None):
        self.parent = parent
        if identifier is None:
            identifier = BNode()
        self.identifier = URIRef(identifier)
        self.prov = Provenance(self, prov)
        self.prov.generate()

    @property
    def graph(self):
        if not hasattr(self, '_graph') or self._graph is None:
            if self.parent.buffered:
                self._graph = Graph(identifier=self.identifier)
            else:
                self._graph = self.parent.graph.get_context(self.identifier)
        return self._graph

    def _triplify_object(self, binding):
        """ Create bi-directional bindings for object relationships. """
        if binding.uri:
            self.graph.add((binding.subject, RDF.type, binding.uri))

        if binding.parent is not None:
            parent = binding.parent.subject
            if binding.parent.is_array:
                parent = binding.parent.parent.subject
            self.graph.add((parent, binding.predicate, binding.subject))
            if binding.reverse is not None:
                self.graph.add((binding.subject, binding.reverse, parent))

        for prop in binding.properties:
            self._triplify(prop)

        return binding.subject

    def _triplify(self, binding):
        """ Recursively generate RDF statement triples from the data and
        schema supplied to the application. """
        if binding.data is None:
            return

        if binding.is_object:
            return self._triplify_object(binding)
        elif binding.is_array:
            for item in binding.items:
                self._triplify(item)
        else:
            subject = binding.parent.subject
            self.graph.add((subject, binding.predicate, binding.object))
            if binding.reverse is not None:
                self.graph.add((binding.object, binding.reverse, subject))

    def add(self, schema, data):
        """ Stage ``data`` as a set of statements, based on the given
        ``schema`` definition. """
        binding = self.get_binding(schema, data)
        return self._triplify(binding)

    def save(self):
        """ Transfer the statements in this context over to the main store. """
        if not self.parent.buffered:
            self.graph.remove((self.identifier, None, None))
            self.prov.generate()
        else:
            query = """
                DELETE WHERE { GRAPH %s { %s ?pred ?val } } ;
                INSERT DATA { GRAPH %s { %s } }
            """
            query = query % (self.identifier.n3(),
                             self.identifier.n3(),
                             self.identifier.n3(),
                             self.graph.serialize(format='nt'))
            self.parent.graph.update(query)
            self.flush()

    def delete(self):
        """ Delete all statements matching the current context identifier
        from the main store. """
        if self.parent.buffered:
            query = 'CLEAR SILENT GRAPH %s ;' % self.identifier.n3()
            self.parent.graph.update(query)
            self.flush()
        else:
            self.graph.remove((None, None, None))

    def flush(self):
        """ Clear all the pending statements in the local context, without
        transferring them to the main store. """
        self._graph = None

    def query(self, q):
        """ Run a query using the jsongraph query dialect. This expects an
        input query, which can either be a dict or a list. """
        return Query(self, None, QueryNode(None, None, q))

    def __str__(self):
        return self.identifier

    def __repr__(self):
        return '<Context("%s")>' % self.identifier
