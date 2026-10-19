import QtQuick
import qs.Commons as Theme

Text {
    textFormat: Text.PlainText
    color: Theme.Color.popups.text
    font.family: Theme.Style.font.family
    font.pixelSize: Theme.Style.font.body
    elide: Text.ElideRight
    maximumLineCount: 1
}
