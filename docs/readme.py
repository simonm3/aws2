# ---
# jupyter:
#   jupytext:
#     text_representation:
#       extension: .py
#       format_name: percent
#       format_version: '1.2'
#       jupytext_version: 1.2.1
#   kernelspec:
#     display_name: Python 3
#     language: python
#     name: python3
# ---

# %% [markdown]
# # Introduction

# %% [markdown]
# This package makes it easy to start and stop AWS spot instances; and simpler to work with AWS resources. The following cells walk through some examples.

# %%
from ipstartup import *
from aws2 import aws, Image, Instance, Volume, Spot, Snapshot, Resource

# %% [markdown]
# # Creating an AMI

# %% [markdown]
# First step is to create a base AMI for our project. We need the id of an existing AMI and then give our project a name. In this case we use one of the fastai Europe Region AMIs and call the image "fastai2". Note you may need to change the defaults:
#
# * security=["default"]
# * key="key"

# %%
Image.copy("ami-9e1a35ed", "fastai2")

# %% [markdown]
# Now we have a base AMI in our account from which we can launch spot instances or standard instances.

# %% [markdown]
# # Starting and stopping a spot instance

# %% [markdown]
# ## Simple version

# %%
i=Spot("fastai2")
i.jupyter()
i.set_ip()

# %% [markdown]
# Now you have an instance named "fastai2" with boot volume named "fastai2". The address is already in the clipboard so can be pasted into your browser address bar. Then you can use jupyter notebooks on the remote server. When you have finished then just stop the instance like this:

# %%
i.stop()

# %% [markdown]
# Now you have a new snapshot named "fastai2" which contains the boot volume from your session; the "fastai2" image now points to the latest snapshot; and the spot instance and volume have been deleted.
#
# Each time you stop:
#
# * You get an additional fastai2 snapshot. The older versions can be deleted via the AWS menus if required. Note snapshots are incremental so the cost of multiple snapshots is low and can be useful to rollback.
# * The image gets replaced. There is only one fastai2 image. This points to the latest fastai2 snapshot.
#
# If AWS terminates your spot instance:
#
# * The stop function will be called automatically
# * As a failsafe, if shutdown occurs without calling stop then the volume will still be present. In this case you can create a snapshot and image manually. No data has been lost until you delete the volume.
#
# Naming of resources uses AWS tags:
#
# * The name "fastai2" is stored as AWS "tag:Name"
# * This is shown on AWS menus as "Name"
# * Note some AWS resource types also have a separate, unconnected "Name" field which may also appear on AWS menus. The latter is not used here as it is inconsistently available and has to be unique.
#
#

# %% [markdown]
# ## Other instance or spot methods

# %% [markdown]
# Launch a standard (non-spot) instance

# %%
i=Instance("fastai2")

# %% [markdown]
# Use python dict syntax for tags

# %%
i.set_tags(someflag="www", another="xxx")
i.tags

# %%
i.terminate()

# %% [markdown]
# # Other utilities

# %% [markdown]
# Get resources sorted with most recent first.

# %%
aws.get_images()

# %% [markdown]
# ....and apply filter

# %%
aws.get_snapshots(Name="fastai2")

# %% [markdown]
# Get list of instance types and spot prices

# %%
df=aws.get_spotprices()
df[df.memory>30].sort_values("SpotPrice")[["memory", "InstanceType", "SpotPrice", "vcpu"]].head(10)

# %% [markdown]
# This is the data that can be extracted from aws for each instance

# %%
df.columns

# %% [markdown]
# Use of python dictionaries for filters and tag filters

# %%
aws.filt(a=4, b="hhhh")

# %%
aws.tfilt(a=4, b="hhhh")

# %% [markdown]
# # Enhanced Network Architecture (ENA)

# %% [markdown]
# Typically AMIs (images) are hardware independent. However there are some exceptions such as ENA. You have to have ENA enabled on the image in order to launch a C5 instance. On the other hand cheaper instance types cannot use ENA. Hence if you are doing simple tasks using a cheap T2 instance and save an image then you will not be able to launch a C5 from that image to do the heavylifting.
#
# The workaround is to stop the spot instance, start a standard instance, stop the instance, change the instance type to C5, enable ENA on the stopped instance, then create the image. Fortunately this can be scripted as below.
#
# It may take up to an hour. However in practice most development and testing can be carried out on non-ENA instances so it is only on release of a production version that you need to create an ENA enabled image.

# %%
i.stop()
i = Instance("fastai2")
i.create_image_ena()

# %% [markdown]
# # Appendix - AWS resources

# %% [markdown]
# These are the main AWS EC2 resource types:
#
# * Instance - a running machine
# * Spot - lower cost instance. This has two disadvantages. Firstly it can be terminated by AWS with just 2 minutes notice in periods of high demand. Secondly it cannot be stopped and started, only terminated.
# * Volume - disk storage for an instance
# * Snapshot - longer term storage that is not attached to a instance
# * Image - the AMI for launching a machine. This is linked to a snapshot of the boot drive.

# %% [markdown]
# Some of the issues with aws/boto3 that are partially addressed here:
#
# * spot instances cannot be stopped only terminated
# * identifying resources by name rather than id
# * filters and tags not in dict format
# * cannot test isinstance(i, ec2.Instance)
# * some common actions are multi-step with waiters in between
# * inconsistent field names e.g. state, State, status
# * waiters only wait for limited number of retries

# %%
