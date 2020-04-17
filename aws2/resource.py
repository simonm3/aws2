import logging

log = logging.getLogger(__name__)


class Resource:
    """ base class to wrap an AWS resource
    """

    res = None

    def __init__(self, res):
        """
        :param res:  Resource, aws resource, aws id, name

        if resource not yet created then just saves name
        """
        from . import Resource

        # Resource
        if isinstance(res, Resource):
            self.__dict__.update(res.__dict__)
            return

        # aws resource
        if str(type(res)).startswith("<class 'boto3.resources.factory.ec2."):
            self.res = res
            return

        # name of existing resource. gets most recent.
        try:
            self.res = self.coll(Name=res)[-1]
            return
        except IndexError:
            pass

        # aws id
        try:
            self.res = [r for r in self.coll() if r.id == res][0]
            return
        except IndexError:
            pass

        # name of new resource to be created
        if not isinstance(res, str):
            raise Exception(
                f"invalid parameter res={res}. Must be Resource, aws.ec2 resource, aws.ec2 id, name"
            )

    def __getattr__(self, attr):
        """ pass undefined calls to embedded aws resource """
        self.refresh()
        return self.res.__getattribute__(attr)

    def __repr__(self):
        """ unique name """
        try:
            return f"{self.name} ({self.id})"
        except:
            return self.name

    def refresh(self):
        """ ensure any values retrieved come from live resource. boto3 resources do not reflect live changes """
        self.res = self.res.__class__(self.res.id)

    @property
    def name(self):
        """ Name with capital letter is shown on aws website """
        return self.tags.get("Name", "")

    @name.setter
    def name(self, value):
        self.set_tags(Name=value)

    @property
    def tags(self):
        """ get tags as a dict """
        self.refresh()
        if not self.res.tags:
            return dict()
        return {tag["Key"]: tag["Value"] for tag in self.res.tags}

    def set_tags(self, **kwargs):
        """ e.g. set tags using key=value e.g. set_tags(name="fred", region="Europe") """
        self.create_tags(Tags=[dict(Key=k, Value=str(v)) for k, v in kwargs.items()])
