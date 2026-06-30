const { registerRoot, Composition } = require('remotion');
const React = require('react');
const { TitleCard } = require('./Composition');

function RemotionRoot() {
  return React.createElement(Composition, {
    id: 'TitleCard',
    component: TitleCard,
    durationInFrames: 150,
    fps: 30,
    width: 1280,
    height: 720,
    defaultProps: { title: '', description: '' },
  });
}

registerRoot(RemotionRoot);
