import os
from glob import glob
from setuptools import find_packages, setup

package_name = 'voice_processing_v2'

setup(
    name=package_name,
    version='0.1.0',
    packages=find_packages(exclude=['test']),
    data_files=[
        ('share/ament_index/resource_index/packages',
            ['resource/' + package_name]),
        ('share/' + package_name, ['package.xml']),
        (os.path.join('share', package_name, 'resource'),
            glob('resource/*.tflite')
            + glob('resource/*.onnx')
            + glob('resource/*.onnx.data')),
    ],
    install_requires=['setuptools'],
    zip_safe=True,
    maintainer='rokey',
    maintainer_email='rokey@todo.todo',
    description='Refactored voice processing package: unified mic control + LLM JSON response',
    license='TODO: License declaration',
    extras_require={
        'test': ['pytest'],
    },
    entry_points={
        'console_scripts': [
            'get_keyword = voice_processing_v2.get_keyword:main',
            'voice_client = voice_processing_v2.voice_client:main',
        ],
    },
)
