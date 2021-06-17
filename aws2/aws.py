"""
miscellaneous aws utilities
    filter resources
    list resources by date
    get resource data

NOTE: This is a set of functions not a class
"""
import logging
import pandas as pd
import boto3
import json
import itertools
import re
from datetime import datetime

log = logging.getLogger(__name__)

ec2 = boto3.resource("ec2")
client = boto3.client("ec2")

# pythonic filters ###########################################


def filt(**kwargs):
    """ get filter from [key=value,...]
    e.g. filt(a=b) => [dict(Name="a", Values=["b"]]
    """
    try:
        kwargs["Name"] = kwargs.pop("name")
    except KeyError:
        pass
    filters = {k: v if isinstance(v, list) else [v] for k, v in kwargs.items()}
    filters = [dict(Name=k.replace("_", "-"), Values=v) for k, v in filters.items()]
    return filters


def tfilt(**kwargs):
    """ prepend tag: to keys before filter
    """
    try:
        kwargs["Name"] = kwargs.pop("name")
    except KeyError:
        pass
    return filt(**{f"tag:{k.replace('_', '-')}": v for k, v in kwargs.items()})


# get filtered lists of resources sorted by date ###############################


def get_instances(**kwargs):
    # add shortcuts to filter
    state = kwargs.pop("state", "")
    r = list(ec2.instances.filter(Filters=tfilt(**kwargs)))
    if state:
        r = [i for i in r if i.state["Name"] == state]
    return sorted(r, key=lambda s: s.launch_time)


def get_images(**kwargs):
    r = list(ec2.images.filter(Owners=["self"], Filters=tfilt(**kwargs)))
    return sorted(r, key=lambda s: s.creation_date)


def get_volumes(**kwargs):
    r = list(ec2.volumes.filter(Filters=tfilt(**kwargs)))
    return sorted(r, key=lambda s: s.create_time)


def get_snapshots(**kwargs):
    r = list(ec2.snapshots.filter(OwnerIds=["self"], Filters=tfilt(**kwargs)))
    return sorted(r, key=lambda s: s.start_time)


def get_ips():
    """ get list of elastic ips """
    return [ip["PublicIp"] for ip in client.describe_addresses()["Addresses"]]


def show_all():
    running = len(get_instances(state="running"))
    log.info(
        f"running={running}; instances={len(get_instances())}; images={len(get_images())}; volumes={len(get_volumes())};"
        f"snapshots={len(get_snapshots())}"
    )


# get dataframe of resource information ######################


def get_instancesdf(**filters):
    """ get dataframe of your instances """
    from . import Instance

    alldata = []
    for i in get_instances(**filters):
        i = Instance(i)
        data = dict(
            name=i.name,
            instance_id=i.instance_id,
            image=i.image_id,
            type=i.instance_type,
            state=i.state["Name"],
            ip=i.public_ip_address,
        )
        tags = i.tags
        tags.pop("Name", None)
        data.update(tags)

        alldata.append(data)
    # fillna for the tags
    return pd.DataFrame(alldata).fillna("")


def get_instancetypes():
    """ return dataframe of instance types/features available in EU
    """
    # API only available in specific regions
    pricing = boto3.client("pricing", "us-east-1")

    pager = pricing.get_paginator("get_products").paginate(
        ServiceCode="AmazonEC2",
        Filters=[
            dict(Type="TERM_MATCH", Field="location", Value="EU (Ireland)"),
            dict(Type="TERM_MATCH", Field="tenancy", Value="Shared"),
            dict(Type="TERM_MATCH", Field="operatingSystem", Value="Linux"),
        ],
        PaginationConfig=dict(MaxItems=1e4),
    )
    pages = [page["PriceList"] for page in pager]
    products = list(itertools.chain.from_iterable(pages))
    attribs = [json.loads(v)["product"]["attributes"] for v in products]
    df = pd.DataFrame(attribs)
    df.columns = standardise(df.columns)
    df = df.loc[df.instance_type.notnull()]
    df.gpu = df.gpu.fillna(0).astype(int)
    df.vcpu = df.vcpu.fillna(0).astype(int)
    df.memory = (
        df.memory.str.replace(",", "")
        .str.extract("(\d+)", expand=False)
        .fillna(0)
        .astype(int)
    )
    df = df[df.memory > 0].drop_duplicates(["instance_type"])

    return df


def get_spotprices():
    """ return dataframe of spot prices

        standardised columns available for query/sort::

        clock_speed, current_generation, dedicated_ebs_throughput, ecu, enhanced_networking_supported, gpu, instance_family, instance_type, intel_avx2available, intel_avx_available, intel_turbo_available, license_model, location, location_type, memory, network_performance, normalization_size_factor, operating_system, operation, physical_processor, pre_installed_sw, processor_architecture, processor_features, servicecode, servicename, storage, tenancy, usagetype, vcpu, availability_zone, spot_price, percpu, per64cpu
    """

    itypes = get_instancetypes()

    # get current spot prices
    pager = client.get_paginator("describe_spot_price_history").paginate(
        StartTime=f"{datetime.utcnow()}Z",
        ProductDescriptions=["Linux/UNIX"],
        PaginationConfig=dict(MaxItems=1e4),
    )
    pages = [page["SpotPriceHistory"] for page in pager]
    pages = list(itertools.chain.from_iterable(pages))
    prices = pd.DataFrame(pages)
    prices.columns = standardise(prices.columns)
    prices = prices[["availability_zone", "instance_type", "spot_price"]]
    prices.spot_price = prices.spot_price.astype(float)

    # merge
    merged = itypes.merge(prices, on="instance_type", how="inner")
    merged["percpu"] = merged.spot_price / merged.vcpu
    merged["per64cpu"] = merged.percpu * 64
    return merged.sort_values("percpu")

def standardise(names):
    """ pep8 names
    :return: list of names that are underscore separated and lower case
    """
    names = [x.strip() for x in names]
    # camelCase to underscore separated
    names = [re.sub("([a-z]+)([A-Z])", r"\1_\2", x) for x in names]
    # non-alphanumeric to underscore
    names = [re.sub("\W+", "_", x) for x in names]
    names = [x.lower() for x in names]
    return names
