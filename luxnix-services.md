# LuxNix Service Setup

LuxNix allows Users to implement their projects or other applications as a Service. Since the NixOS configuration of LuxNix handles the whole network architecture, it is adamant that the roles for certain services nees to be specified.

## EndoReg Client Role

An EndoReg client is a study laptop in the network of local data processing laptops, for example inside clinics or inside your working group data hub. Here, data can be imported or exported locally in an anonymized state. For example using lx-annotate and lx-anonymizer to manipulate the local endoreg-db.

These clients usually feature a small nvidia gpu, that allows them to run ai models like the ResNet segmentation model or the ocr and llm needed for lx anonymizer anonymization and data extraction.

## Server Role

A server serves as an access point for remote laptops that might reach out to the central instance to run larger ai models or data processing in the background. This is possible, after the data has been anonymized, annotated and exported from the study clients. This role therefore has different network settings and allows for a different scale of data processing which is why its services are defined elsewhere in LuxNix

## Config

The config of a service is taken from the role, e.g. endoreg client, and then overwritten with options. That could be local directory setups or other settings.


