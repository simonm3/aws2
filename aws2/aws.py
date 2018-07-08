"""
miscellaneous aws utilities
    filter resources
    list resources by date
    get resource data

NOTE: This is a set of functions not a class
"""
import logging as log

import pandas as pd
import boto3
import json
import itertools
from datetime import datetime

ec2 = boto3.resource('ec2')
client = boto3.client('ec2')

# pythonic filters ###########################################

def filt(**kwargs):
    """ get filter from [key=value,...]
    e.g. filt(a=b) => [dict(Name="a", Values=["b"]]
    """
    filters = {k:v if isinstance(v,list) else [v] for k,v in kwargs.items()}
    filters = [dict(Name=k, Values=v) for k, v in filters.items()]
    return filters

def tfilt(**kwargs):
    """ get tag filter from [key=value,...]. prepend "tag:" to keys.
    e.g. tfilt(a=b) => [dict(Name="tag:a", Values=["b"]]
    """
    return filt(**{"tag:"+k: v for k, v in kwargs.items()})

# get filtered lists of resources sorted by date ###############################

def get_instances(**kwargs):
    r = list(ec2.instances.filter(Filters=tfilt(**kwargs)))
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


# get dataframe of resource information ######################


def get_instancesdf():
    """ get dataframe of your instances """
    from . import Instance
    a = []
    for i in get_instances():
        i = Instance(i)
        a.append([i.Name, i.instance_id, i.image.image_id,
                  i.instance_type, i.state["Name"],
                  i.public_ip_address])
    return pd.DataFrame(a, columns=["name", "instance_id", "image", "type",
                                    "state", "ip"])


def get_instancetypes():
    """ return dataframe of instance types/features available in EU
    """
    # API only available in specific regions
    pricing = boto3.client('pricing', 'us-east-1')

    pager = pricing.get_paginator('get_products')\
        .paginate(ServiceCode="AmazonEC2",
                  Filters=[dict(Type="TERM_MATCH",
                                Field="location", Value="EU (Ireland)"),
                           dict(Type="TERM_MATCH",
                                Field="tenancy", Value="Shared"),
                           dict(Type="TERM_MATCH",
                                Field="operatingSystem", Value="Linux")],
                  PaginationConfig=dict(MaxItems=1e4))
    pages = [page["PriceList"] for page in pager]
    products = list(itertools.chain.from_iterable(pages))
    attribs = [json.loads(v)["product"]["attributes"] for v in products]
    df = pd.DataFrame(attribs)
    df = df.loc[df.instanceType.notnull()]
    df = df.rename(columns=dict(instanceType="InstanceType"))
    df.gpu = df.gpu.fillna(0).astype(int)
    df.vcpu = df.vcpu.fillna(0).astype(int)
    df.memory = df.memory.str.replace(",","").str.extract('(\d+)', expand=False)\
        .fillna(0).astype(int)
    df = df[df.memory > 0].drop_duplicates(["InstanceType"])
    return df


def get_spotprices():
    """ return dataframe of spot prices """

    itypes = get_instancetypes()

    # get current spot prices
    pager = client.get_paginator('describe_spot_price_history')\
        .paginate(StartTime=f"{datetime.utcnow()}Z",
                  ProductDescriptions=['Linux/UNIX'],
                  PaginationConfig=dict(MaxItems=1e4))
    pages = [page["SpotPriceHistory"] for page in pager]
    pages = list(itertools.chain.from_iterable(pages))
    prices = pd.DataFrame(pages)
    prices = prices[["AvailabilityZone", "InstanceType", "SpotPrice"]]
    prices.SpotPrice = prices.SpotPrice.astype(float)

    # merge
    merged = itypes.merge(prices, on="InstanceType", how="inner")
    merged["percpu"] = merged.SpotPrice/merged.vcpu
    merged["per64cpu"] = merged.percpu*64
    return merged.sort_values("percpu")
