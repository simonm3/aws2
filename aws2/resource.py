import logging as log

class Resource:
    """ base class to wrap an AWS resource

    children: Instance, Volume, Snapshot, Image
    descendants: Spot, Dockerspot
    """
    res = None
    _Name = None

    def __init__(self, res):
        """
        res: AWS resource, id or name
        if resource not yet created then just saves name
        """
        # existing resource
        if isinstance(res, Resource):
            self.res = res.res
            return

        # existing AWS resource
        if not isinstance(res, str):
            self.res = res
            return
        
        # existing name
        try:
            # most recent aws resource with name
            self.res = self.coll(Name=res)[-1]
            return
        except IndexError:
            pass

        # existing id
        try:
            self.res = [r for r in self.coll() if r.id==res][0]
            return
        except IndexError:
            pass

        # new resource to be wrapped later
        self._Name = res

    def __getattr__(self, attr):
        """ pass undefined calls to embedded aws resource """
        return self.res.__getattribute__(attr)

    def __repr__(self):
        """ unique name """
        try:
            return f"{self.Name} ({self.id})"
        except:
            return self.Name

    @property
    def Name(self):
        """ return aws name or local name """
        try:
            return self.tags["Name"]
        except Exception:
            return self._Name
    def name(self):
        """ avoids spelling error """
        return self.Name

    @Name.setter
    def Name(self, value):
        """ if resource exists set aws name else set local placeholder name
        """
        try:
            self.set_tags(Name=value)
        except Exception:
            self._Name = value

    @property
    def tags(self):
        """ get tags as a dict """
        return {tag["Key"]: tag["Value"] for tag in self.res.tags}

    def set_tags(self, **kwargs):
        """ e.g. set tags using key=value e.g. set_tags(Name="fred", region="Europe") """
        self.create_tags(Tags=[dict(Key=k, Value=v)
                               for k, v in kwargs.items()])

