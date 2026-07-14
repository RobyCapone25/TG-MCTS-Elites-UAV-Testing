# Aerialist image containing PX4, PX4-Avoidance, ROS, and Gazebo.
FROM skhatiri/aerialist:2.0

# Make the Aerialist Python package available inside the project container.
RUN python3 -m pip install --no-cache-dir -e /src/aerialist/

WORKDIR /src/generator/

COPY requirements.txt ./requirements.txt
RUN python3 -m pip install --no-cache-dir -r requirements.txt

COPY . /src/generator/

RUN mkdir -p logs results generated_tests \
    && chmod +x scripts/*.sh

ENV AGENT=local \
    PYTHONPATH=/src/generator/src \
    MPLBACKEND=Agg \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    AVOIDANCE_LAUNCH=/src/aerialist/aerialist/resources/simulation/collision_prevention.launch \
    AVOIDANCE_BOX=/src/aerialist/aerialist/resources/simulation/box.xacro
