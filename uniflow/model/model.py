"""Model Module."""
import copy
import json
import logging
import re
from typing import Any, Dict, List

from uniflow.model.config import ModelConfig
from uniflow.model.server import ModelServerFactory

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

RESPONSE = "response"
ERROR = "error"
MAX_ATTEMPTS = 3


class Model:
    """Model Class."""

    def __init__(
        self,
        model_server: str,
        few_shot_template: Dict[str, Any],
        model_config: Dict[str, Any],
    ) -> None:
        """Initialize Model class.

        Args:
            model_server (str): Model server name.
            few_shot_template (Dict[str, Any]): Few shot template.
            model_config (Dict[str, Any]): Model config.
        """
        model_server_cls = ModelServerFactory.get(model_server)
        self._model_server = model_server_cls(model_config)
        self._few_shot_template = few_shot_template

    def _serialize(self, data: Dict[str, Any]) -> str:
        output_strings = []

        # Iterate over each key-value pair in the dictionary
        for key, value in data.items():
            if isinstance(value, list):
                # Special handling for the "examples" list
                for example in value:
                    for ex_key, ex_value in example.items():
                        output_strings.append(f"{ex_key}: {ex_value}")
            else:
                output_strings.append(f"{key}: {value}")

        # Join all the strings into one large string, separated by new lines
        output_string = "\n".join(output_strings)
        return output_string

    def _deserialize(self, data: List[str]) -> List[Dict[str, Any]]:
        """Deserialize data.

        Args:
            data (List[str]): Data to deserialize.

        Returns:
            Dict[str, Any]: Deserialized data.
        """
        return {
            RESPONSE: data,
            ERROR: "Failed to deserialize 0 examples",
        }

    def run(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """Run model.

        Args:
            data (Dict[str, Any]): Data to run.

        Returns:
            Dict[str, Any]: Output data.
        """
        serialized_data = self._serialize(data)

        for i in range(MAX_ATTEMPTS):
            data = self._model_server(serialized_data)
            data = self._deserialize(data)
            if data[RESPONSE]:
                break
            logger.info("Attempt %s failed, retrying...", i + 1)

        return data


class FewShotModel(Model):
    """Few Shot Model Class."""

    def __init__(
        self,
        model_server: str,
        model_config: ModelConfig,
        few_shot_template: Dict[str, Any],
    ) -> None:
        super().__init__(model_server, few_shot_template, model_config)
        assert len(few_shot_template) == 2, "Few shot template must have 2 keys"
        # get keys from few shot template examples
        self._template_keys = list(few_shot_template.keys())
        self._example_keys = list(few_shot_template[self._template_keys[1]][0].keys())
        self._data = dict()

    def _serialize(self, data: Dict[str, Any]) -> str:
        """Serialize data.

        Args:
            data (Dict[str, Any]): Data to serialize.

        Returns:
            str: Serialized data.
        """
        self._data = data
        few_shot_template = copy.deepcopy(self._few_shot_template)
        few_shot_template[self._template_keys[1]].append(data)

        output_strings = []

        # Iterate over each key-value pair in the dictionary
        for key, value in few_shot_template.items():
            if isinstance(value, list):
                # Special handling for the "examples" list
                for example in value:
                    for ex_key, ex_value in example.items():
                        output_strings.append(f"{ex_key}: {ex_value}")
            else:
                output_strings.append(f"{key}: {value}")

        # Join all the strings into one large string, separated by new lines
        output_string = "\n".join(output_strings)
        return output_string

    def _deserialize(self, data: List[str]) -> List[Dict[str, Any]]:
        def filter_data(d: str) -> Dict[str, str]:
            """Filter data."""
            pattern = "|".join(map(re.escape, self._example_keys))

            segments = [
                segment.strip(" :\n") for segment in re.split(pattern, d.lower())
            ]

            result = dict()
            result.update(self._data)
            result.update(
                {
                    self._example_keys[-2]: segments[-2],
                    self._example_keys[-1]: segments[-1],
                }
            )
            return result

        error_count = 0
        output_list = []

        for d in data:
            try:
                output_list.append(filter_data(d))
            except Exception:
                error_count += 1
                continue

        return {
            RESPONSE: output_list,
            ERROR: f"Failed to deserialize {error_count} examples",
        }


class JsonModel(Model):
    """Json Model Class."""

    def _serialize(self, data: Dict[str, Any]) -> str:
        """Serialize data.

        Args:
            data (Dict[str, Any]): Data to serialize.

        Returns:
            str: Serialized data.
        """
        few_shot_template = copy.deepcopy(self._few_shot_template)
        few_shot_template.update(data)
        return json.dumps(few_shot_template)

    def _deserialize(self, data: List[str]) -> List[Dict[str, Any]]:
        """Deserialize data.

        Args:
            data (List[str]): Data to deserialize.

        Returns:
            Dict[str, Any]: Deserialized data.
        """
        output_list = []
        error_count = 0

        for d in data:
            try:
                output_list.append(json.loads(d))
            except Exception:
                error_count += 1
                continue
        return {
            RESPONSE: output_list,
            ERROR: f"Failed to deserialize {error_count} examples",
        }


class OpenAIJsonModel(JsonModel):
    """OpenAI Json Model Class.

    This is a bit strange because OpenAI's JSON API doesn't return JSON.
    """

    def _serialize(self, data: Dict[str, Any]) -> str:
        output_strings = []

        # Iterate over each key-value pair in the dictionary
        for key, value in data.items():
            if isinstance(value, list):
                # Special handling for the "examples" list
                for example in value:
                    for ex_key, ex_value in example.items():
                        output_strings.append(f"{ex_key}: {ex_value}")
            else:
                output_strings.append(f"{key}: {value}")

        # Join all the strings into one large string, separated by new lines
        output_string = "\n".join(output_strings)
        return output_string
