# -*- coding: utf-8 -*-
# Generated by the protocol buffer compiler.  DO NOT EDIT!
# NO CHECKED-IN PROTOBUF GENCODE
# source: span.proto
# Protobuf Python Version: 5.28.1
"""Generated protocol buffer code."""
from google.protobuf import descriptor as _descriptor
from google.protobuf import descriptor_pool as _descriptor_pool
from google.protobuf import runtime_version as _runtime_version
from google.protobuf import symbol_database as _symbol_database
from google.protobuf.internal import builder as _builder

_runtime_version.ValidateProtobufRuntimeVersion(
    _runtime_version.Domain.PUBLIC, 5, 28, 1, "", "span.proto"
)
# @@protoc_insertion_point(imports)

_sym_db = _symbol_database.Default()


DESCRIPTOR = _descriptor_pool.Default().AddSerializedFile(
    b'\n\nspan.proto\x12\x02pb"\xcf\x02\n\x04Span\x12\x0f\n\x07service\x18\x01 \x01(\t\x12\x0c\n\x04name\x18\x02 \x01(\t\x12\x10\n\x08resource\x18\x03 \x01(\t\x12\x0f\n\x07traceID\x18\x04 \x01(\x04\x12\x0e\n\x06spanID\x18\x05 \x01(\x04\x12\x10\n\x08parentID\x18\x06 \x01(\x04\x12\r\n\x05start\x18\x07 \x01(\x03\x12\x10\n\x08\x64uration\x18\x08 \x01(\x03\x12\r\n\x05\x65rror\x18\t \x01(\x05\x12 \n\x04meta\x18\n \x03(\x0b\x32\x12.pb.Span.MetaEntry\x12&\n\x07metrics\x18\x0b \x03(\x0b\x32\x15.pb.Span.MetricsEntry\x12\x0c\n\x04type\x18\x0c \x01(\t\x1a+\n\tMetaEntry\x12\x0b\n\x03key\x18\x01 \x01(\t\x12\r\n\x05value\x18\x02 \x01(\t:\x02\x38\x01\x1a.\n\x0cMetricsEntry\x12\x0b\n\x03key\x18\x01 \x01(\t\x12\r\n\x05value\x18\x02 \x01(\x01:\x02\x38\x01\x62\x06proto3'
)

_globals = globals()
_builder.BuildMessageAndEnumDescriptors(DESCRIPTOR, _globals)
_builder.BuildTopDescriptorsAndMessages(DESCRIPTOR, "span_pb2", _globals)
if not _descriptor._USE_C_DESCRIPTORS:
    DESCRIPTOR._loaded_options = None
    _globals["_SPAN_METAENTRY"]._loaded_options = None
    _globals["_SPAN_METAENTRY"]._serialized_options = b"8\001"
    _globals["_SPAN_METRICSENTRY"]._loaded_options = None
    _globals["_SPAN_METRICSENTRY"]._serialized_options = b"8\001"
    _globals["_SPAN"]._serialized_start = 19
    _globals["_SPAN"]._serialized_end = 354
    _globals["_SPAN_METAENTRY"]._serialized_start = 263
    _globals["_SPAN_METAENTRY"]._serialized_end = 306
    _globals["_SPAN_METRICSENTRY"]._serialized_start = 308
    _globals["_SPAN_METRICSENTRY"]._serialized_end = 354
# @@protoc_insertion_point(module_scope)
