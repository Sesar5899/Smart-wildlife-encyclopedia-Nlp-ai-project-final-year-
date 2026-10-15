/* Markdown rendering for chat answers.
 *
 * The model is asked for GitHub-flavoured Markdown, so the chat has to draw
 * it: tables above all, because a comparison written as a table and shown as
 * pipes and dashes is unreadable.  Everything is HTML-escaped first and the
 * markup is then built from the escaped text, so a reply can never inject
 * elements, attributes or scripts into the page.
 */
(function (global) {
  'use strict';

  function escapeHtml(value) {
    return String(value === null || value === undefined ? '' : value)
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;')
      .replace(/'/g, '&#039;');
  }

  // Only absolute http(s) and site-relative targets become links: a reply is
  // never allowed to produce a javascript: or data: URL.
  var SAFE_LINK = /^(https?:\/\/[^\s]+|\/[^\s]*)$/;

  function inlineMarkup(escaped) {
    return escaped
      .replace(/`([^`\n]+)`/g, '<code>$1</code>')
      .replace(/\*\*([^*\n]+)\*\*/g, '<strong>$1</strong>')
      .replace(/(^|[^*])\*([^*\n]+)\*(?!\*)/g, '$1<em>$2</em>')
      .replace(/(^|[^_])__([^_\n]+)__(?!_)/g, '$1<strong>$2</strong>')
      .replace(/\[([^\]\n]+)\]\(([^\s)]+)\)/g, function (whole, label, href) {
        var target = href.replace(/&amp;/g, '&');
        if (!SAFE_LINK.test(target)) return label;
        var external = /^https?:\/\//.test(target);
        return '<a href="' + escapeHtml(target) + '"' +
          (external ? ' target="_blank" rel="noopener noreferrer"' : '') +
          '>' + label + '</a>';
      });
  }

  function splitRow(line) {
    var text = line.trim();
    if (text.charAt(0) === '|') text = text.slice(1);
    if (text.charAt(text.length - 1) === '|') text = text.slice(0, -1);
    return text.split('|').map(function (cell) { return cell.trim(); });
  }

  function isTableRow(line) {
    return line.indexOf('|') !== -1;
  }

  function isDelimiterRow(line) {
    var cells = splitRow(line);
    if (!cells.length) return false;
    return cells.every(function (cell) { return /^:?-{1,}:?$/.test(cell); });
  }

  function alignmentOf(cell) {
    var left = cell.charAt(0) === ':';
    var right = cell.charAt(cell.length - 1) === ':';
    if (left && right) return 'center';
    if (right) return 'right';
    if (left) return 'left';
    return '';
  }

  function cellHtml(tag, value, alignment) {
    var style = alignment ? ' style="text-align:' + alignment + '"' : '';
    return '<' + tag + style + '>' + inlineMarkup(escapeHtml(value)) + '</' + tag + '>';
  }

  function renderTable(lines, start) {
    // A table is a header row, a |---|---| delimiter, then body rows. Without
    // the delimiter the pipes are ordinary text and stay ordinary text.
    if (!isTableRow(lines[start]) || start + 1 >= lines.length) return null;
    if (!isTableRow(lines[start + 1]) || !isDelimiterRow(lines[start + 1])) return null;

    var header = splitRow(lines[start]);
    var alignments = splitRow(lines[start + 1]).map(alignmentOf);
    var index = start + 2;
    var body = [];
    while (index < lines.length && lines[index].trim() && isTableRow(lines[index])) {
      body.push(splitRow(lines[index]));
      index += 1;
    }

    var html = '<div class="md-table-wrap"><table class="md-table"><thead><tr>';
    header.forEach(function (cell, column) {
      html += cellHtml('th', cell, alignments[column] || '');
    });
    html += '</tr></thead><tbody>';
    body.forEach(function (row) {
      html += '<tr>';
      for (var column = 0; column < header.length; column += 1) {
        html += cellHtml('td', row[column] === undefined ? '' : row[column],
          alignments[column] || '');
      }
      html += '</tr>';
    });
    return { html: html + '</tbody></table></div>', next: index };
  }

  function renderList(lines, start, ordered) {
    var pattern = ordered ? /^\s*\d+[.)]\s+(.*)$/ : /^\s*[-*+]\s+(.*)$/;
    var index = start;
    var items = [];
    while (index < lines.length) {
      var match = lines[index].match(pattern);
      if (!match) break;
      items.push(match[1]);
      index += 1;
    }
    var tag = ordered ? 'ol' : 'ul';
    var html = '<' + tag + ' class="md-list">';
    items.forEach(function (item) {
      html += '<li>' + inlineMarkup(escapeHtml(item)) + '</li>';
    });
    return { html: html + '</' + tag + '>', next: index };
  }

  function renderMarkdown(text) {
    var lines = String(text === null || text === undefined ? '' : text)
      .replace(/\r\n?/g, '\n')
      .split('\n');
    var html = '';
    var index = 0;

    while (index < lines.length) {
      var line = lines[index];
      var trimmed = line.trim();

      if (!trimmed) { index += 1; continue; }

      if (/^```/.test(trimmed)) {
        var code = [];
        index += 1;
        while (index < lines.length && !/^```/.test(lines[index].trim())) {
          code.push(lines[index]);
          index += 1;
        }
        index += 1;  // the closing fence, or the end of a still-streaming reply
        html += '<pre class="md-code"><code>' + escapeHtml(code.join('\n')) + '</code></pre>';
        continue;
      }

      var table = renderTable(lines, index);
      if (table) { html += table.html; index = table.next; continue; }

      var heading = trimmed.match(/^(#{1,6})\s+(.*)$/);
      if (heading) {
        var level = Math.min(heading[1].length + 2, 6);
        html += '<h' + level + ' class="md-heading">' +
          inlineMarkup(escapeHtml(heading[2])) + '</h' + level + '>';
        index += 1;
        continue;
      }

      if (/^(-{3,}|\*{3,}|_{3,})$/.test(trimmed)) {
        html += '<hr class="md-rule">';
        index += 1;
        continue;
      }

      if (/^>\s?/.test(trimmed)) {
        var quote = [];
        while (index < lines.length && /^\s*>\s?/.test(lines[index])) {
          quote.push(lines[index].replace(/^\s*>\s?/, ''));
          index += 1;
        }
        html += '<blockquote class="md-quote">' +
          inlineMarkup(escapeHtml(quote.join('\n'))).replace(/\n/g, '<br>') +
          '</blockquote>';
        continue;
      }

      if (/^\s*[-*+]\s+/.test(line)) {
        var bullets = renderList(lines, index, false);
        html += bullets.html;
        index = bullets.next;
        continue;
      }

      if (/^\s*\d+[.)]\s+/.test(line)) {
        var numbered = renderList(lines, index, true);
        html += numbered.html;
        index = numbered.next;
        continue;
      }

      var paragraph = [];
      while (index < lines.length) {
        var current = lines[index];
        if (!current.trim()) break;
        if (/^```/.test(current.trim())) break;
        if (/^\s*[-*+]\s+/.test(current) || /^\s*\d+[.)]\s+/.test(current)) break;
        if (/^\s*>/.test(current)) break;
        if (/^#{1,6}\s+/.test(current.trim())) break;
        if (renderTable(lines, index)) break;
        paragraph.push(current.trim());
        index += 1;
      }
      html += '<p class="md-paragraph">' +
        inlineMarkup(escapeHtml(paragraph.join('\n'))).replace(/\n/g, '<br>') +
        '</p>';
    }

    return html;
  }

  // Mirrors plain_snippet() on the server: one readable line of an answer,
  // for the history rail. Cell and list markers become spaces rather than
  // vanishing, so a table does not collapse into one run-on word.
  var MARKDOWN_NOISE = /^\s*[-*+]\s+|^\s*#{1,6}\s+|^\s*>\s?|^\s*\|?\s*:?-{2,}:?\s*(\|\s*:?-{2,}:?\s*)*\|?\s*$/gm;

  function markdownToText(text) {
    return String(text === null || text === undefined ? '' : text)
      .replace(MARKDOWN_NOISE, ' ')
      .replace(/[|`]/g, ' ')
      .replace(/\*\*|__/g, '')
      .replace(/\s+/g, ' ')
      .trim();
  }

  global.renderMarkdown = renderMarkdown;
  global.markdownToText = markdownToText;
  global.escapeChatHtml = escapeHtml;
}(window));
