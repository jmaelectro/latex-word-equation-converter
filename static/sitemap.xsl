<?xml version="1.0" encoding="UTF-8"?>
<xsl:stylesheet version="1.0"
    xmlns:xsl="http://www.w3.org/1999/XSL/Transform"
    xmlns:s="http://www.sitemaps.org/schemas/sitemap/0.9"
    xmlns:xhtml="http://www.w3.org/1999/xhtml">

  <xsl:output method="html" encoding="UTF-8" indent="yes"/>

  <xsl:template match="/">
    <html>
      <head>
        <title>Sitemap</title>
        <meta charset="UTF-8"/>
        <style>
          body { font-family: Arial, sans-serif; margin: 20px; }
          table { border-collapse: collapse; width: 100%; }
          th, td { border: 1px solid #ddd; padding: 8px; }
          th { background: #f5f5f5; text-align: left; }
          tr:nth-child(even) { background: #fafafa; }
          .small { color: #666; font-size: 12px; }
        </style>
      </head>
      <body>
        <h1>Sitemap</h1>
        <p class="small">Vista amigable para humanos. Los buscadores usan el XML.</p>
        <table>
          <tr>
            <th>URL</th>
            <th>Lastmod</th>
            <th>Changefreq</th>
            <th>Priority</th>
            <th>Alternates (hreflang)</th>
          </tr>
          <xsl:for-each select="s:urlset/s:url">
            <tr>
              <td><a href="{s:loc}"><xsl:value-of select="s:loc"/></a></td>
              <td><xsl:value-of select="s:lastmod"/></td>
              <td><xsl:value-of select="s:changefreq"/></td>
              <td><xsl:value-of select="s:priority"/></td>
              <td>
                <xsl:for-each select="xhtml:link">
                  <div class="small">
                    <xsl:value-of select="@hreflang"/>:
                    <xsl:text> </xsl:text>
                    <xsl:value-of select="@href"/>
                  </div>
                </xsl:for-each>
              </td>
            </tr>
          </xsl:for-each>
        </table>
      </body>
    </html>
  </xsl:template>
</xsl:stylesheet>
