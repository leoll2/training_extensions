"""
Model inference demostration tool.
"""

# Copyright (C) 2021 Intel Corporation
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
# http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing,
# software distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions
# and limitations under the License.

import argparse

import cv2
from ote_sdk.configuration.helper import create
from ote_sdk.entities.annotation import AnnotationSceneEntity, AnnotationSceneKind
from ote_sdk.entities.datasets import DatasetEntity, DatasetItemEntity
from ote_sdk.entities.id import ID
from ote_sdk.entities.image import Image
from ote_sdk.entities.inference_parameters import InferenceParameters
from ote_sdk.entities.label import LabelEntity
from ote_sdk.entities.label_schema import LabelSchemaEntity
from ote_sdk.entities.model import ModelEntity
from ote_sdk.entities.task_environment import TaskEnvironment
from ote_sdk.usecases.adapters.model_adapter import ModelAdapter

from ote_cli.registry import find_and_parse_model_template
from ote_cli.tools.utils.demo.images_capture import open_images_capture
from ote_cli.tools.utils.demo.visualization import draw_predictions
from ote_cli.utils.config import override_parameters
from ote_cli.utils.importing import get_impl_class
from ote_cli.utils.loading import load_model_weights
from ote_cli.utils.parser import (
    add_hyper_parameters_sub_parser,
    gen_params_dict_from_args,
)

ESC_BUTTON = 27


def parse_args():
    """
    Parses command line arguments.
    """

    pre_parser = argparse.ArgumentParser(add_help=False)
    pre_parser.add_argument("template")
    parsed, _ = pre_parser.parse_known_args()
    # Load template.yaml file.
    template = find_and_parse_model_template(parsed.template)
    # Get hyper parameters schema.
    hyper_parameters = template.hyper_parameters.data
    assert hyper_parameters

    parser = argparse.ArgumentParser()
    parser.add_argument("template")
    parser.add_argument(
        "-i",
        "--input",
        required=True,
        help="Source of input data: images folder, image, webcam.",
    )
    parser.add_argument(
        "--load-weights",
        required=True,
        help="Load only weights from previously saved checkpoint",
    )
    parser.add_argument(
        "--fit-to-size",
        nargs=2,
        type=int,
        help="Fit displayed images to window with specified Width and height. It is about visualization only.",
    )
    parser.add_argument("--loop", action="store_true")
    parser.add_argument("--delay", type=int, default=3)
    parser.add_argument("--labels", nargs="+")

    add_hyper_parameters_sub_parser(parser, hyper_parameters, modes=("INFERENCE",))

    return parser.parse_args(), template, hyper_parameters


def get_predictions(task, frame):
    empty_annotation = AnnotationSceneEntity(
        annotations=[], kind=AnnotationSceneKind.PREDICTION
    )

    item = DatasetItemEntity(
        media=Image(frame),
        annotation_scene=empty_annotation,
    )

    dataset = DatasetEntity(items=[item])

    predicted_validation_dataset = task.infer(
        dataset,
        InferenceParameters(is_evaluation=True),
    )
    item = predicted_validation_dataset[0]
    return item.annotation_scene.annotations


def main():
    """
    Main function that is used for model evaluation.
    """

    # Dynamically create an argument parser based on override parameters.
    args, template, hyper_parameters = parse_args()
    # Get new values from user's input.
    updated_hyper_parameters = gen_params_dict_from_args(args)
    # Override overridden parameters by user's values.
    override_parameters(updated_hyper_parameters, hyper_parameters)

    hyper_parameters = create(hyper_parameters)

    labels = [
        LabelEntity(l, template.task_type, id=ID(i)) for i, l in enumerate(args.labels)
    ]

    # Get classes for Task, ConfigurableParameters and Dataset.
    taks_class = get_impl_class(template.entrypoints.base)
    environment = TaskEnvironment(
        model=None,
        hyper_parameters=hyper_parameters,
        label_schema=LabelSchemaEntity.from_labels(labels),
        model_template=template,
    )

    model_adapters = {
        "weights.pth": ModelAdapter(load_model_weights(args.load_weights))
    }
    model = ModelEntity(
        configuration=environment.get_model_configuration(),
        model_adapters=model_adapters,
        train_dataset=None,
    )
    environment.model = model

    task = taks_class(task_environment=environment)

    capture = open_images_capture(args.input, args.loop)

    while True:
        frame = capture.read()
        if frame is None:
            break

        predictions = get_predictions(task, frame)
        frame = draw_predictions(
            template.task_type, predictions, frame, args.fit_to_size
        )

        cv2.imshow("frame", frame)
        if cv2.waitKey(args.delay) == ESC_BUTTON:
            break
